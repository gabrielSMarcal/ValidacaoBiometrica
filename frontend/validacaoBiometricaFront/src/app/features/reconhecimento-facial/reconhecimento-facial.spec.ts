import { ComponentFixture, TestBed } from '@angular/core/testing';
import { WritableSignal, signal } from '@angular/core';
import { Router, provideRouter } from '@angular/router';
import type { Detection } from '@mediapipe/tasks-vision';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { Frame } from '../../core/models/biometria/biometria.model';
import { AuthService } from '../../core/services/auth.service';
import { UsuarioService } from '../../core/services/usuario.service';
import { CAPTURE_POLICY, SINGLE_FACE_MESSAGE } from './capture-validation';
import { ReconhecimentoFacial } from './reconhecimento-facial';

interface Sample {
  pixels: Uint8ClampedArray;
  detections: Detection[];
}

interface CaptureInternals {
  enrollmentUserId: number;
  stableDetections: number;
  cameraState: WritableSignal<string>;
  errorMessage: WritableSignal<string>;
  statusMessage: WritableSignal<string>;
  biometricFailures: WritableSignal<number>;
  captureInProgress: WritableSignal<boolean>;
  readCameraSample(): Sample;
  captureFrame(pixels: Uint8ClampedArray): Frame;
  pauseCapture(): Promise<void>;
  handleCaptureError(error: unknown): void;
}

function observation(pose = 0): Detection {
  return {
    boundingBox: { originX: 160, originY: 48, width: 320, height: 384, angle: 0 },
    categories: [],
    keypoints: [{ x: 0.4, y: 0.4 }, { x: 0.6, y: 0.4 }, { x: 0.5 + pose * 0.2, y: 0.55 }],
  };
}

function image(detections: Detection[] = [observation()], dark = false): Sample {
  const pixels = new Uint8ClampedArray(CAPTURE_POLICY.width * CAPTURE_POLICY.height * 4);
  for (let y = 0; y < CAPTURE_POLICY.height; y += 1) {
    for (let x = 0; x < CAPTURE_POLICY.width; x += 1) {
      const index = (y * CAPTURE_POLICY.width + x) * 4;
      const value = dark ? 10 : x < 320 ? 70 : 170;
      pixels[index] = pixels[index + 1] = pixels[index + 2] = value;
      pixels[index + 3] = 255;
    }
  }
  return { pixels, detections };
}

describe('ReconhecimentoFacial', () => {
  let component: ReconhecimentoFacial;
  let fixture: ComponentFixture<ReconhecimentoFacial>;
  let internals: CaptureInternals;
  let navigate: ReturnType<typeof vi.spyOn>;
  const api = {
    verificarBiometria: vi.fn(),
    atualizarBiometria: vi.fn(),
  };
  const auth = { currentUser: signal(null), concluirAutenticacao: vi.fn() };
  const accepted = { usuario: { nivel: 1 }, processamento: {} };

  beforeEach(async () => {
    api.verificarBiometria.mockReset().mockReturnValue(of(accepted));
    api.atualizarBiometria.mockReset().mockReturnValue(of(accepted));
    auth.concluirAutenticacao.mockReset();
    await TestBed.configureTestingModule({
      imports: [ReconhecimentoFacial],
      providers: [
        provideRouter([]),
        { provide: UsuarioService, useValue: api },
        { provide: AuthService, useValue: auth },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(ReconhecimentoFacial);
    component = fixture.componentInstance;
    internals = component as unknown as CaptureInternals;
    navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    await fixture.whenStable();
  });

  afterEach(() => {
    fixture.destroy();
    vi.restoreAllMocks();
  });

  function ready(samples: Sample[]): ReturnType<typeof vi.fn> {
    internals.cameraState.set('detectando');
    internals.stableDetections = CAPTURE_POLICY.stableSamples;
    let index = 0;
    const read = vi.fn(() => {
      if (index >= samples.length) {
        throw new Error('Sequência de teste esgotada.');
      }
      return samples[index++];
    });
    vi.spyOn(internals, 'readCameraSample').mockImplementation(read);
    vi.spyOn(internals, 'pauseCapture').mockResolvedValue();
    let frame = 0;
    vi.spyOn(internals, 'captureFrame').mockImplementation(() => ({
      largura: 640, altura: 480, rgb_base64: `quadro-${++frame}`,
    }));
    return read;
  }

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('valida o login diretamente com três quadros, sem pedir movimentos', async () => {
    const sample = image();
    const read = ready([sample, sample, sample]);
    const messages = vi.spyOn(internals.statusMessage, 'set');
    await component.capturarReconhecimento();
    expect(read).toHaveBeenCalledTimes(3);
    expect(api.verificarBiometria).toHaveBeenCalledWith({ frames: [
      { largura: 640, altura: 480, rgb_base64: 'quadro-1' },
      { largura: 640, altura: 480, rgb_base64: 'quadro-2' },
      { largura: 640, altura: 480, rgb_base64: 'quadro-3' },
    ] });
    expect(api.atualizarBiometria).not.toHaveBeenCalled();
    expect(messages.mock.calls.flat().join(' ')).not.toContain('sua direita');
    expect(messages.mock.calls.flat().join(' ')).not.toContain('sua esquerda');
  });

  it('no cadastro espera frente, direita e esquerda antes de enviar um único lote', async () => {
    internals.enrollmentUserId = 12;
    const front = image([observation(0)]);
    const right = image([observation(-0.1)]);
    const left = image([observation(0.1)]);
    const read = ready([front, front, front, front, right, right, right, left, left, left]);
    const messages = vi.spyOn(internals.statusMessage, 'set');
    await component.capturarReconhecimento();
    expect(read).toHaveBeenCalledTimes(10);
    expect(api.atualizarBiometria).toHaveBeenCalledOnce();
    const [userId, body] = api.atualizarBiometria.mock.calls[0];
    expect(userId).toBe(12);
    expect(Object.keys(body)).toEqual(['frames']);
    expect(body.frames).toHaveLength(3);
    expect(api.verificarBiometria).not.toHaveBeenCalled();
    expect(messages.mock.calls.flat().join(' ')).toContain('sua direita');
    expect(messages.mock.calls.flat().join(' ')).toContain('sua esquerda');
  });

  it('não avança com imagem idêntica mesmo que o detector sugira a pose seguinte', async () => {
    internals.enrollmentUserId = 12;
    const front = image([observation(0)]);
    const right = image([observation(-0.1)]);
    const left = image([observation(0.1)]);
    ready([front, front, front, right, right, right, right, right, right, left, left, left]);
    vi.mocked(internals.captureFrame)
      .mockReturnValueOnce({ largura: 640, altura: 480, rgb_base64: 'repetido' })
      .mockReturnValueOnce({ largura: 640, altura: 480, rgb_base64: 'repetido' })
      .mockReturnValueOnce({ largura: 640, altura: 480, rgb_base64: 'direita' })
      .mockReturnValueOnce({ largura: 640, altura: 480, rgb_base64: 'esquerda' });
    const messages = vi.spyOn(internals.statusMessage, 'set');
    await component.capturarReconhecimento();
    expect(internals.captureFrame).toHaveBeenCalledTimes(4);
    expect(api.atualizarBiometria.mock.calls[0][1].frames.map((frame: Frame) => frame.rgb_base64))
      .toEqual(['repetido', 'direita', 'esquerda']);
    expect(messages.mock.calls.flat().join(' ')).toContain('idêntica');
  });

  it('descarta o lote inteiro se aparecer uma segunda pessoa no meio do cadastro', async () => {
    internals.enrollmentUserId = 12;
    const front = image();
    ready([front, front, front, image([observation(), observation()])]);
    await component.capturarReconhecimento();
    expect(internals.captureFrame).toHaveBeenCalledOnce();
    expect(api.atualizarBiometria).not.toHaveBeenCalled();
    expect(api.verificarBiometria).not.toHaveBeenCalled();
    expect(internals.errorMessage()).toBe(SINGLE_FACE_MESSAGE);
    expect(internals.biometricFailures()).toBe(0);
    expect(internals.cameraState()).toBe('detectando');
  });

  it('bloqueia a validação direta se houver várias pessoas em qualquer quadro', async () => {
    ready([image(), image([observation(), observation()])]);
    await component.capturarReconhecimento();
    expect(api.verificarBiometria).not.toHaveBeenCalled();
    expect(internals.errorMessage()).toBe(SINGLE_FACE_MESSAGE);
    expect(internals.biometricFailures()).toBe(0);
  });

  it('aguarda a correção da luz antes de aceitar o quadro', async () => {
    const read = ready([image([observation()], true), image(), image(), image()]);
    const messages = vi.spyOn(internals.statusMessage, 'set');
    await component.capturarReconhecimento();
    expect(read).toHaveBeenCalledTimes(4);
    expect(internals.captureFrame).toHaveBeenCalledTimes(3);
    expect(api.verificarBiometria).toHaveBeenCalledOnce();
    expect(messages.mock.calls.flat().join(' ')).toContain('muito escuro');
    expect(internals.biometricFailures()).toBe(0);
  });

  it('preserva o motivo de captura inválida da API, sem contá-lo como identidade incorreta', async () => {
    ready([image(), image(), image()]);
    api.verificarBiometria.mockReturnValue(throwError(() => ({
      status: 422, detail: 'Quadro 2: O rosto está muito escuro. Aumente a iluminação.',
    })));
    await component.capturarReconhecimento();
    expect(internals.errorMessage()).toBe('Quadro 2: O rosto está muito escuro. Aumente a iluminação.');
    expect(internals.biometricFailures()).toBe(0);
    expect(internals.cameraState()).toBe('detectando');
    expect(navigate).not.toHaveBeenCalled();
  });

  it('mantém a recusa visível e permite nova captura com o desafio ainda válido', () => {
    const error = { status: 401, detail: 'CPF e senha foram confirmados, mas a biometria não correspondeu.' };
    internals.handleCaptureError(error);
    expect(internals.cameraState()).toBe('detectando');
    expect(internals.biometricFailures()).toBe(1);
    expect(internals.errorMessage()).toBe(error.detail);
    expect(navigate).not.toHaveBeenCalled();
    internals.handleCaptureError(error);
    internals.handleCaptureError(error);
    expect(internals.cameraState()).toBe('erro');
    expect(internals.errorMessage()).toContain(error.detail);
    expect(internals.errorMessage()).toContain('Volte ao login');
    expect(navigate).not.toHaveBeenCalled();
  });

  it('explica desafio expirado sem redirecionar antes de o usuário ler o motivo', () => {
    internals.handleCaptureError({ status: 401, detail: 'O prazo da biometria expirou. Informe CPF e senha novamente.' });
    expect(internals.cameraState()).toBe('erro');
    expect(internals.errorMessage()).toContain('O prazo da biometria expirou.');
    expect(navigate).not.toHaveBeenCalled();
  });

  it('cancelar a tela durante uma etapa não envia um lote parcial', async () => {
    internals.enrollmentUserId = 12;
    ready([image()]);
    vi.mocked(internals.pauseCapture).mockRestore();
    const capture = component.capturarReconhecimento();
    fixture.destroy();
    await capture;
    expect(api.atualizarBiometria).not.toHaveBeenCalled();
    expect(api.verificarBiometria).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalled();
  });
});
