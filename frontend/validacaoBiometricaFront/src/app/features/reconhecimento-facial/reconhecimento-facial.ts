import { AfterViewInit, Component, ElementRef, OnDestroy, inject, signal, viewChild } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { FaceDetector, FilesetResolver } from '@mediapipe/tasks-vision';
import { firstValueFrom } from 'rxjs';

import { Frame } from '../../core/models/biometria/biometria.model';
import { AuthService } from '../../core/services/auth.service';
import { ApiError } from '../../core/models/validation-error/api-error.model';
import { UsuarioService } from '../../core/services/usuario.service';

@Component({
  imports: [RouterLink],
  selector: 'app-reconhecimento-facial',
  styleUrl: './reconhecimento-facial.css',
  templateUrl: './reconhecimento-facial.html',
})
export class ReconhecimentoFacial implements AfterViewInit, OnDestroy {
  protected readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly usuarioService = inject(UsuarioService);
  protected readonly video = viewChild.required<ElementRef<HTMLVideoElement>>('video');
  protected readonly cameraState = signal<'abrindo' | 'detectando' | 'capturando' | 'erro'>('abrindo');
  protected readonly statusMessage = signal('Solicitando acesso à câmera…');
  protected readonly errorMessage = signal('');
  protected readonly captureInProgress = signal(false);
  protected readonly biometricFailures = signal(0);
  private readonly canvas = document.createElement('canvas');
  private stream: MediaStream | null = null;
  private faceDetector: FaceDetector | null = null;
  private detectionTimer: ReturnType<typeof setTimeout> | null = null;
  private stableDetections = 0;
  private readonly enrollmentUserId = Number(this.route.snapshot.queryParamMap.get('cadastroId'));

  ngAfterViewInit(): void {
    void this.openCamera();
  }

  ngOnDestroy(): void {
    this.stopCamera();
  }

  async openCamera(): Promise<void> {
    if (!navigator.mediaDevices?.getUserMedia) {
      this.showCameraError('Este navegador não oferece acesso à câmera.');
      return;
    }

    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: 'user',
          width: { ideal: 640, max: 640 },
          height: { ideal: 480, max: 480 },
        },
      });
      const videoElement = this.video().nativeElement;
      videoElement.srcObject = this.stream;
      await videoElement.play();
      this.statusMessage.set('Carregando detector facial…');
      const vision = await FilesetResolver.forVisionTasks(
        'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.1.1/wasm',
      );
      this.faceDetector = await FaceDetector.createFromOptions(vision, {
        baseOptions: {
          modelAssetPath:
            'https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite',
        },
        runningMode: 'VIDEO',
        minDetectionConfidence: 0.6,
      });
      this.cameraState.set('detectando');
      this.statusMessage.set('Posicione seu rosto dentro do guia para iniciar a captura.');
      this.scheduleFaceDetection();
    } catch (error: unknown) {
      if (this.stream === null) {
        const message = error instanceof DOMException && error.name === 'NotAllowedError'
          ? 'Permita o acesso à câmera para realizar o reconhecimento facial.'
          : 'Não foi possível abrir a câmera. Verifique se ela está disponível e tente novamente.';
        this.showCameraError(message);
        return;
      }

      this.cameraState.set('erro');
      this.statusMessage.set('Detector facial indisponível.');
      this.errorMessage.set(
        'Não foi possível carregar o detector facial. Verifique sua conexão e recarregue a página.',
      );
    }
  }

  async capturarReconhecimento(): Promise<void> {
    if (this.cameraState() !== 'detectando' || this.captureInProgress()) {
      return;
    }

    this.captureInProgress.set(true);
    this.cameraState.set('capturando');
    this.errorMessage.set('');
    this.statusMessage.set('Capturando quadros. Mantenha o rosto no guia…');

    try {
      const frames: Frame[] = [];
      for (let index = 0; index < 4; index += 1) {
        frames.push(this.captureFrame());
        await this.wait(150);
      }

      if (this.isEnrollment()) {
        await firstValueFrom(this.usuarioService.atualizarBiometria(this.enrollmentUserId, { frames }));
        this.stopCamera();
        void this.router.navigateByUrl('/gerenciamento-usuarios');
        return;
      }

      const resposta = await firstValueFrom(this.usuarioService.verificarBiometria({ frames }));
      this.auth.concluirAutenticacao(resposta);
      this.stopCamera();
      void this.router.navigateByUrl(resposta.usuario.nivel === 4
        ? '/painel-admin'
        : '/restricted-dashboard');
    } catch (error: unknown) {
      const failures = this.biometricFailures() + 1;
      this.biometricFailures.set(failures);
      if (failures >= 3) {
        this.stopCamera();
        this.statusMessage.set('A biometria falhou três vezes. Retornando ao login…');
        this.errorMessage.set('Por segurança, inicie uma nova autenticação.');
        void this.router.navigateByUrl('/login');
        return;
      }

      this.cameraState.set('detectando');
      this.statusMessage.set(`A captura não foi concluída. Tentativa ${failures} de 3.`);
      this.errorMessage.set(this.getErrorMessage(error));
      this.scheduleFaceDetection();
    } finally {
      this.captureInProgress.set(false);
    }
  }

  confirmarReconhecimento(): void {
    void this.capturarReconhecimento();
  }

  private scheduleFaceDetection(): void {
    if (this.detectionTimer !== null || this.cameraState() !== 'detectando') {
      return;
    }
    this.detectionTimer = setTimeout(() => {
      this.detectionTimer = null;
      void this.detectFace();
    }, 200);
  }

  private async detectFace(): Promise<void> {
    if (this.cameraState() !== 'detectando' || !this.faceDetector) {
      return;
    }

    try {
      const detections = this.faceDetector.detectForVideo(
        this.video().nativeElement,
        performance.now(),
      );
      const face = detections.detections[0]?.boundingBox;
      if (!face || !this.isFaceInsideGuide(face)) {
        this.stableDetections = 0;
        this.statusMessage.set('Centralize o rosto dentro do guia para iniciar a captura.');
      } else {
        this.stableDetections += 1;
        this.statusMessage.set(
          this.stableDetections >= 3
            ? 'Rosto detectado. Capturando…'
            : 'Rosto detectado. Permaneça imóvel…',
        );
        if (this.stableDetections >= 3) {
          await this.capturarReconhecimento();
          return;
        }
      }
    } catch {
      this.stableDetections = 0;
      this.errorMessage.set('Não foi possível analisar a imagem da câmera. Tente novamente.');
    }

    this.scheduleFaceDetection();
  }

  private isFaceInsideGuide(face: {
    originX: number;
    originY: number;
    width: number;
    height: number;
  }): boolean {
    const videoElement = this.video().nativeElement;
    const width = videoElement.videoWidth;
    const height = videoElement.videoHeight;
    if (!width || !height) {
      return false;
    }

    const centerX = (face.originX + face.width / 2) / width;
    const centerY = (face.originY + face.height / 2) / height;
    const faceWidth = face.width / width;
    const faceHeight = face.height / height;
    return centerX >= 0.25 && centerX <= 0.75
      && centerY >= 0.1 && centerY <= 0.9
      && faceWidth >= 0.2 && faceWidth <= 0.7
      && faceHeight >= 0.25 && faceHeight <= 0.95;
  }

  private captureFrame(): Frame {
    const videoElement = this.video().nativeElement;
    const largura = 640;
    const altura = 480;
    this.canvas.width = largura;
    this.canvas.height = altura;
    const context = this.canvas.getContext('2d');

    if (!context || videoElement.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
      throw new Error('A câmera ainda não está pronta para capturar uma imagem.');
    }

    context.drawImage(videoElement, 0, 0, largura, altura);
    const pixels = context.getImageData(0, 0, largura, altura).data;
    const rgb = new Uint8Array(largura * altura * 3);

    for (let source = 0, target = 0; source < pixels.length; source += 4) {
      rgb[target] = pixels[source];
      rgb[target + 1] = pixels[source + 1];
      rgb[target + 2] = pixels[source + 2];
      target += 3;
    }

    let binary = '';
    const chunkSize = 0x8000;
    for (let index = 0; index < rgb.length; index += chunkSize) {
      binary += String.fromCharCode(...rgb.subarray(index, index + chunkSize));
    }

    return { largura, altura, rgb_base64: btoa(binary) };
  }

  private stopCamera(): void {
    if (this.detectionTimer !== null) {
      clearTimeout(this.detectionTimer);
      this.detectionTimer = null;
    }
    this.faceDetector = null;
    this.stableDetections = 0;
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    const videoElement = this.video?.()?.nativeElement;
    if (videoElement) {
      videoElement.srcObject = null;
    }
  }

  private showCameraError(message: string): void {
    this.cameraState.set('erro');
    this.statusMessage.set('Câmera indisponível.');
    this.errorMessage.set(message);
  }

  private getErrorMessage(error: unknown): string {
    if (error instanceof Error) {
      return error.message;
    }
    if (this.isApiError(error)) {
      if (typeof error.detail === 'string') {
        return error.detail;
      }
      const validationMessage = error.detail
        .map((item) => item.msg)
        .filter(Boolean)
        .join(' ');
      if (validationMessage) {
        return validationMessage;
      }
    }
    return 'Não foi possível validar a biometria. Tente novamente.';
  }

  private isEnrollment(): boolean {
    return Number.isInteger(this.enrollmentUserId) && this.enrollmentUserId > 0;
  }

  private isApiError(error: unknown): error is ApiError & {
    detail: { msg: string }[];
  } {
    return typeof error === 'object'
      && error !== null
      && 'status' in error
      && 'detail' in error;
  }

  private wait(milliseconds: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, milliseconds));
  }
}
