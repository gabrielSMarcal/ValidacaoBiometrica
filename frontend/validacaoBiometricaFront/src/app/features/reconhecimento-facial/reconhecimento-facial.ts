import { Component, ElementRef, OnDestroy, OnInit, computed, inject, signal, viewChild } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Detection, FaceDetector, FilesetResolver } from '@mediapipe/tasks-vision';
import { Subject, firstValueFrom, takeUntil } from 'rxjs';

import { Frame } from '../../core/models/biometria/biometria.model';
import { AuthService } from '../../core/services/auth.service';
import { CadastroPendenteService } from '../../core/services/cadastro-pendente.service';
import { ApiError } from '../../core/models/validation-error/api-error.model';
import { UsuarioService } from '../../core/services/usuario.service';
import {
  CAPTURE_POLICY, ENROLLMENT_INSTRUCTIONS, SINGLE_FACE_MESSAGE,
  enrollmentPoseMessage, faceInsideGuide, frameExposureMessage, horizontalPose, illuminationMessage, matchesEnrollmentPose,
} from './capture-validation';

interface CameraSample {
  pixels: Uint8ClampedArray;
  detections: Detection[];
}

class CaptureCancelled extends Error {}

@Component({
  imports: [RouterLink],
  selector: 'app-reconhecimento-facial',
  styleUrl: './reconhecimento-facial.css',
  templateUrl: './reconhecimento-facial.html',
})
export class ReconhecimentoFacial implements OnInit, OnDestroy {
  protected readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly usuarioService = inject(UsuarioService);
  private readonly cadastroPendente = inject(CadastroPendenteService);
  protected readonly enrollment = this.route.snapshot.queryParamMap.get('cadastro') === 'novo'
    || this.route.snapshot.queryParamMap.has('cadastroId');
  protected readonly greetingName = computed(() => this.enrollment
    ? this.cadastroPendente.dados()?.nome ?? ''
    : this.auth.pendingUser()?.nome ?? this.auth.currentUser()?.nome ?? '');
  protected readonly captureStep = signal(-1);
  protected readonly validating = signal(false);
  protected readonly requiresLogin = signal(false);
  protected readonly video = viewChild<ElementRef<HTMLVideoElement>>('video');
  protected readonly cameraState = signal<'fechada' | 'abrindo' | 'detectando' | 'capturando' | 'erro'>('fechada');
  protected readonly statusMessage = signal('Abra a câmera para iniciar a validação facial.');
  protected readonly errorMessage = signal('');
  protected readonly captureInProgress = signal(false);
  protected readonly captureCooldown = signal(0);
  protected readonly biometricFailures = signal(0);
  private readonly canvas = document.createElement('canvas');
  private readonly destroyed$ = new Subject<void>();
  private stream: MediaStream | null = null;
  private faceDetector: FaceDetector | null = null;
  private detectionTimer: ReturnType<typeof setTimeout> | null = null;
  private cooldownTimer: ReturnType<typeof setInterval> | null = null;
  private captureWait: { timer: ReturnType<typeof setTimeout>; resolve: () => void } | null = null;
  private stableDetections = 0;
  private captureGeneration = 0;
  private lastDetectionTimestamp = 0;
  private destroyed = false;

  ngOnInit(): void {
    if (this.enrollment && !this.cadastroPendente.dados()) {
      this.requiresLogin.set(true);
      void this.router.navigateByUrl('/cadastro-usuario');
    }
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    this.destroyed$.next();
    this.destroyed$.complete();
    this.stopCamera();
    if (this.enrollment) {
      this.cadastroPendente.limpar();
    }
  }

  async openCamera(): Promise<void> {
    if (this.destroyed || this.requiresLogin() || this.cameraState() === 'abrindo'
      || this.cameraState() === 'detectando' || this.cameraState() === 'capturando') {
      return;
    }
    this.stopCamera();
    const generation = this.captureGeneration;
    this.cameraState.set('abrindo');
    this.statusMessage.set('Solicitando acesso à câmera…');
    this.errorMessage.set('');
    if (!navigator.mediaDevices?.getUserMedia) {
      this.showCameraError('Este navegador não oferece acesso à câmera.');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: 'user',
          width: { ideal: CAPTURE_POLICY.width, max: CAPTURE_POLICY.width },
          height: { ideal: CAPTURE_POLICY.height, max: CAPTURE_POLICY.height },
        },
      });
      if (this.destroyed || generation !== this.captureGeneration) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      this.stream = stream;
      const videoElement = this.video()?.nativeElement;
      if (!videoElement) {
        this.showCameraError('Não foi possível preparar a visualização da câmera.');
        return;
      }
      videoElement.srcObject = stream;
      await videoElement.play();
      if (this.destroyed || generation !== this.captureGeneration) {
        return;
      }
      this.statusMessage.set('Carregando detector facial…');
      const vision = await FilesetResolver.forVisionTasks(
        'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.1.1/wasm',
      );
      if (this.destroyed || generation !== this.captureGeneration) {
        return;
      }
      const detector = await FaceDetector.createFromOptions(vision, {
        baseOptions: {
          modelAssetPath:
            'https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite',
        },
        runningMode: 'VIDEO',
        minDetectionConfidence: 0.6,
      });
      if (this.destroyed || generation !== this.captureGeneration) {
        detector.close();
        return;
      }
      this.faceDetector = detector;
      this.lastDetectionTimestamp = 0;
      this.cameraState.set('detectando');
      this.statusMessage.set('Posicione somente o seu rosto dentro do guia e aguarde a detecção.');
      this.scheduleFaceDetection();
    } catch (error: unknown) {
      if (this.destroyed || generation !== this.captureGeneration) {
        return;
      }
      const message = error instanceof DOMException && error.name === 'NotAllowedError'
        ? 'Permita o acesso à câmera para realizar o reconhecimento facial.'
        : this.stream === null
          ? 'Não foi possível abrir a câmera. Verifique se ela está disponível e tente novamente.'
          : 'Não foi possível preparar o detector facial. Verifique sua conexão e tente abrir a câmera novamente.';
      this.showCameraError(message);
    }
  }

  async capturarReconhecimento(): Promise<void> {
    if (this.cameraState() !== 'detectando' || this.captureInProgress()
      || this.captureCooldown() > 0 || this.requiresLogin() || this.destroyed) {
      return;
    }
    if (this.stableDetections < CAPTURE_POLICY.stableSamples) {
      this.errorMessage.set('Aguarde a detecção de um único rosto bem iluminado dentro do guia antes de fazer a captura.');
      return;
    }
    this.cancelPreviewTimer();
    const generation = ++this.captureGeneration;
    this.captureInProgress.set(true);
    this.cameraState.set('capturando');
    this.errorMessage.set('');
    try {
      const frames = await this.captureSequence(generation);
      this.assertCurrentCapture(generation);
      this.validating.set(true);
      this.statusMessage.set(this.enrollment
        ? 'Validando o rosto e concluindo o cadastro…'
        : 'Confirmando seu acesso…');
      if (this.isEnrollment()) {
        const dados = this.cadastroPendente.dados();
        if (!dados) {
          throw new Error('Os dados do cadastro não estão mais disponíveis. Volte ao cadastro e preencha os dados novamente.');
        }
        await firstValueFrom(this.usuarioService.cadastrarUsuario({ ...dados, frames })
          .pipe(takeUntil(this.destroyed$)));
        this.assertCurrentCapture(generation);
        this.cadastroPendente.limpar();
        this.stopCamera();
        void this.router.navigateByUrl('/gerenciamento-usuarios', {
          state: { cadastroConcluido: true },
        });
        return;
      }
      const resposta = await firstValueFrom(this.usuarioService.verificarBiometria({ frames })
        .pipe(takeUntil(this.destroyed$)));
      this.assertCurrentCapture(generation);
      this.auth.concluirAutenticacao(resposta);
      this.stopCamera();
      void this.router.navigateByUrl(resposta.usuario.nivel === 4 ? '/painel-admin' : '/restricted-dashboard');
    } catch (error: unknown) {
      if (error instanceof CaptureCancelled || this.destroyed || generation !== this.captureGeneration) {
        return;
      }
      this.handleCaptureError(error);
    } finally {
      this.validating.set(false);
      if (!this.destroyed && generation === this.captureGeneration) {
        this.captureInProgress.set(false);
        if (this.cameraState() === 'detectando') {
          this.startCaptureCooldown();
          this.scheduleFaceDetection();
        }
      }
    }
  }

  confirmarReconhecimento(): void {
    void this.capturarReconhecimento();
  }

  private async captureSequence(generation: number): Promise<Frame[]> {
    const frames: Frame[] = [];
    let frontalPose: number | null = null;
    let firstTurnPose: number | null = null;
    const enrollment = this.isEnrollment();
    const frameCount = enrollment ? CAPTURE_POLICY.enrollmentFrameCount : CAPTURE_POLICY.frameCount;
    for (let step = 0; step < frameCount; step += 1) {
      this.captureStep.set(step);
      const instruction = enrollment
        ? ENROLLMENT_INSTRUCTIONS[step]
        : 'Olhe de frente para a câmera e fique parado por um instante.';
      this.statusMessage.set(instruction);
      const deadline = performance.now() + CAPTURE_POLICY.stepTimeoutMs;
      let stable = 0;
      let lastReason = instruction;
      while (true) {
        this.assertCurrentCapture(generation);
        if (performance.now() >= deadline) {
          throw new Error(`O tempo da etapa ${step + 1} terminou. ${lastReason} Clique em "Fazer captura" para tentar novamente.`);
        }
        const sample = this.readCameraSample();
        const reason = this.sampleProblem(sample);
        if (reason !== null) {
          stable = 0;
          lastReason = reason;
          this.statusMessage.set(reason);
          await this.pauseCapture();
          continue;
        }
        const pose = enrollment
          ? horizontalPose(sample.detections[0], CAPTURE_POLICY.width, CAPTURE_POLICY.height)
          : null;
        if (enrollment && !matchesEnrollmentPose(pose, step, frontalPose, firstTurnPose)) {
          stable = 0;
          lastReason = enrollmentPoseMessage(pose, step, frontalPose, firstTurnPose);
          this.statusMessage.set(lastReason);
          await this.pauseCapture();
          continue;
        }
        stable += 1;
        if (enrollment && stable < CAPTURE_POLICY.stableSamples) {
          this.statusMessage.set(instruction);
          await this.pauseCapture();
          continue;
        }
        const frame = this.captureFrame(sample.pixels);
        if (enrollment && frames.some((previous) => previous.rgb_base64 === frame.rgb_base64)) {
          stable = 0;
          lastReason = `${instruction} A imagem continua idêntica à anterior; mova o rosto levemente.`;
          this.statusMessage.set(lastReason);
          await this.pauseCapture();
          continue;
        }
        frames.push(frame);
        if (step === 0) {
          frontalPose = pose;
        } else if (step === 1) {
          firstTurnPose = pose;
        }
        break;
      }
      await this.pauseCapture();
    }
    this.assertCurrentCapture(generation);
    return frames;
  }

  private sampleProblem(sample: CameraSample): string | null {
    if (sample.detections.length > 1) {
      throw new Error(SINGLE_FACE_MESSAGE);
    }
    const face = sample.detections[0]?.boundingBox;
    if (sample.detections.length !== 1 || !face) {
      return frameExposureMessage(sample.pixels)
        ?? 'Nenhum rosto detectado. Posicione o rosto inteiro na câmera e ajuste a iluminação à sua frente.';
    }
    if (!faceInsideGuide(face, CAPTURE_POLICY.width, CAPTURE_POLICY.height)) {
      return 'Centralize o rosto inteiro dentro do guia, mantendo os dois olhos visíveis.';
    }
    return illuminationMessage(sample.pixels, CAPTURE_POLICY.width, CAPTURE_POLICY.height, face);
  }

  private readCameraSample(): CameraSample {
    const videoElement = this.video()?.nativeElement;
    if (!videoElement || !this.faceDetector || videoElement.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
      throw new Error('A câmera ainda não está pronta para capturar uma imagem.');
    }
    this.canvas.width = CAPTURE_POLICY.width;
    this.canvas.height = CAPTURE_POLICY.height;
    const context = this.canvas.getContext('2d', { willReadFrequently: true });
    if (!context) {
      throw new Error('Não foi possível ler os quadros da câmera.');
    }
    context.drawImage(videoElement, 0, 0, this.canvas.width, this.canvas.height);
    const pixels = context.getImageData(0, 0, this.canvas.width, this.canvas.height).data;
    this.lastDetectionTimestamp = Math.max(performance.now(), this.lastDetectionTimestamp + 1);
    // Detecta e captura os mesmos pixels, sem uma segunda leitura do vídeo.
    const result = this.faceDetector.detectForVideo(this.canvas, this.lastDetectionTimestamp);
    return { pixels, detections: result.detections };
  }

  private scheduleFaceDetection(): void {
    if (this.detectionTimer !== null || this.cameraState() !== 'detectando' || this.destroyed) {
      return;
    }
    this.detectionTimer = setTimeout(() => {
      this.detectionTimer = null;
      this.detectFace();
    }, CAPTURE_POLICY.sampleIntervalMs);
  }

  private detectFace(): void {
    if (this.cameraState() !== 'detectando' || !this.faceDetector || this.destroyed) {
      return;
    }
    try {
      const sample = this.readCameraSample();
      const reason = this.sampleProblem(sample);
      const pose = this.isEnrollment() && reason === null
        ? horizontalPose(sample.detections[0], CAPTURE_POLICY.width, CAPTURE_POLICY.height)
        : null;
      if (reason !== null || (this.isEnrollment() && !matchesEnrollmentPose(pose, 0, null))) {
        this.stableDetections = 0;
        this.statusMessage.set(reason ?? ENROLLMENT_INSTRUCTIONS[0]);
      } else {
        this.stableDetections += 1;
        this.statusMessage.set(this.stableDetections >= CAPTURE_POLICY.stableSamples
          ? 'Um único rosto detectado. Clique em "Fazer captura" para continuar.'
          : 'Rosto detectado. Aguarde um instante…');
      }
    } catch (error: unknown) {
      this.stableDetections = 0;
      this.statusMessage.set(this.getErrorMessage(error));
    }
    this.scheduleFaceDetection();
  }

  private captureFrame(pixels: Uint8ClampedArray): Frame {
    const rgb = new Uint8Array(CAPTURE_POLICY.width * CAPTURE_POLICY.height * 3);
    for (let source = 0, target = 0; source < pixels.length; source += 4) {
      rgb[target++] = pixels[source];
      rgb[target++] = pixels[source + 1];
      rgb[target++] = pixels[source + 2];
    }
    let binary = '';
    const chunkSize = 0x8000;
    for (let index = 0; index < rgb.length; index += chunkSize) {
      binary += String.fromCharCode(...rgb.subarray(index, index + chunkSize));
    }
    return { largura: CAPTURE_POLICY.width, altura: CAPTURE_POLICY.height, rgb_base64: btoa(binary) };
  }

  private handleCaptureError(error: unknown): void {
    const message = this.getErrorMessage(error);
    this.captureStep.set(-1);
    if (this.isApiError(error) && error.status === 401) {
      const mismatch = !this.isEnrollment() && message.includes('biometria não correspondeu');
      if (mismatch) {
        this.biometricFailures.update((count) => count + 1);
      }
      if (!mismatch || this.biometricFailures() >= 3) {
        this.requiresLogin.set(true);
        this.stopCamera();
        this.cameraState.set('erro');
        this.statusMessage.set('Inicie uma nova autenticação pelo link "Voltar para o login".');
        this.errorMessage.set(`${message} Volte ao login e confirme CPF e senha novamente.`);
        return;
      }
    }
    this.stableDetections = 0;
    this.cameraState.set('detectando');
    this.statusMessage.set('A captura não foi concluída. Corrija o motivo informado e faça uma nova captura.');
    this.errorMessage.set(message);
  }

  private assertCurrentCapture(generation: number): void {
    if (this.destroyed || generation !== this.captureGeneration || this.cameraState() !== 'capturando') {
      throw new CaptureCancelled();
    }
  }

  private cancelPreviewTimer(): void {
    if (this.detectionTimer !== null) {
      clearTimeout(this.detectionTimer);
      this.detectionTimer = null;
    }
  }

  private stopCamera(): void {
    this.captureGeneration += 1;
    this.cancelPreviewTimer();
    this.stopCooldown();
    if (this.captureWait !== null) {
      clearTimeout(this.captureWait.timer);
      const resolve = this.captureWait.resolve;
      this.captureWait = null;
      resolve();
    }
    this.faceDetector?.close();
    this.faceDetector = null;
    this.stableDetections = 0;
    this.captureInProgress.set(false);
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    const videoElement = this.video()?.nativeElement;
    if (videoElement) {
      videoElement.srcObject = null;
    }
  }

  private startCaptureCooldown(): void {
    this.stopCooldown();
    this.captureCooldown.set(3);
    this.cooldownTimer = setInterval(() => {
      this.captureCooldown.update((seconds) => {
        if (seconds <= 1) {
          this.stopCooldown();
          return 0;
        }
        return seconds - 1;
      });
    }, 1000);
  }

  private stopCooldown(): void {
    if (this.cooldownTimer !== null) {
      clearInterval(this.cooldownTimer);
      this.cooldownTimer = null;
    }
    this.captureCooldown.set(0);
  }

  private showCameraError(message: string): void {
    this.stopCamera();
    this.cameraState.set('erro');
    this.statusMessage.set('Câmera indisponível.');
    this.errorMessage.set(message);
  }

  private getErrorMessage(error: unknown): string {
    if (this.isApiError(error)) {
      if (error.status === 0) {
        return 'Não foi possível comunicar com a API. Verifique sua conexão e tente novamente.';
      }
      if (typeof error.detail === 'string') {
        return error.detail;
      }
      const validationMessage = error.detail.map((item) => item.msg).filter(Boolean).join(' ');
      if (validationMessage) {
        return validationMessage;
      }
    }
    return error instanceof Error ? error.message : 'Não foi possível validar a biometria. Tente novamente.';
  }

  private isEnrollment(): boolean {
    return this.enrollment;
  }

  private isApiError(error: unknown): error is ApiError {
    return typeof error === 'object' && error !== null
      && 'status' in error && typeof error.status === 'number' && 'detail' in error
      && (typeof error.detail === 'string' || Array.isArray(error.detail));
  }

  private pauseCapture(): Promise<void> {
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        this.captureWait = null;
        resolve();
      }, CAPTURE_POLICY.sampleIntervalMs);
      this.captureWait = { timer, resolve };
    });
  }
}
