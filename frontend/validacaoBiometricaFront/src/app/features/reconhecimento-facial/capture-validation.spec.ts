import type { Detection } from '@mediapipe/tasks-vision';
import {
  CAPTURE_POLICY, FaceBox, faceInsideGuide, frameExposureMessage,
  horizontalPose, illuminationMessage, matchesEnrollmentPose,
} from './capture-validation';

const width = 640;
const height = 480;
const face: FaceBox = { originX: 160, originY: 48, width: 320, height: 384, angle: 0 };

function detection(pose = 0): Detection {
  return {
    boundingBox: face, categories: [],
    keypoints: [{ x: 0.4, y: 0.4 }, { x: 0.6, y: 0.4 }, { x: 0.5 + pose * 0.2, y: 0.55 }],
  };
}

function pixels(gray: (x: number, y: number) => number): Uint8ClampedArray {
  const values = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const index = (y * width + x) * 4;
      values[index] = values[index + 1] = values[index + 2] = gray(x, y);
      values[index + 3] = 255;
    }
  }
  return values;
}

describe('validação local dos quadros', () => {
  it('calcula o deslocamento normalizado do nariz e distingue direita de esquerda', () => {
    expect(horizontalPose(detection(0), width, height)).toBeCloseTo(0);
    expect(horizontalPose(detection(-0.1), width, height)).toBeCloseTo(-0.1);
    expect(horizontalPose(detection(0.1), width, height)).toBeCloseTo(0.1);
    expect(matchesEnrollmentPose(0, 0, null)).toBe(true);
    expect(matchesEnrollmentPose(-0.1, 1, 0)).toBe(true);
    expect(matchesEnrollmentPose(0.1, 2, 0)).toBe(true);
    expect(matchesEnrollmentPose(0.1, 1, 0)).toBe(false);
    expect(matchesEnrollmentPose(-0.1, 2, 0)).toBe(false);
  });

  it('translação e escala não simulam a mudança de posição solicitada', () => {
    const original = detection();
    const translated = {
      ...original,
      keypoints: original.keypoints.map((point) => ({ x: point.x * 0.5 + 0.1, y: point.y * 0.5 + 0.2 })),
    };
    expect(horizontalPose(translated, width, height)).toBeCloseTo(0);
    expect(matchesEnrollmentPose(horizontalPose(translated, width, height), 1, 0)).toBe(false);
    expect(matchesEnrollmentPose(horizontalPose(translated, width, height), 2, 0)).toBe(false);
  });

  it('preserva a razão em coordenadas de pixels quando há inclinação', () => {
    const initial = detection(-0.1);
    const angle = Math.PI / 9;
    const tilted = {
      ...initial,
      keypoints: initial.keypoints.map((point) => {
        const x = point.x * width - 320;
        const y = point.y * height - 240;
        return {
          x: (Math.cos(angle) * x - Math.sin(angle) * y + 320) / width,
          y: (Math.sin(angle) * x + Math.cos(angle) * y + 240) / height,
        };
      }),
    };
    expect(horizontalPose(tilted, width, height)).toBeCloseTo(-0.1);
  });

  it('não aceita perfil excessivo, pontos ausentes ou rosto parado na etapa lateral', () => {
    expect(matchesEnrollmentPose(0, 1, 0)).toBe(false);
    expect(matchesEnrollmentPose(0, 2, 0)).toBe(false);
    expect(matchesEnrollmentPose(CAPTURE_POLICY.poseLimit + 0.1, 2, 0)).toBe(false);
    expect(horizontalPose({ ...detection(), keypoints: [] }, width, height)).toBeNull();
    expect(horizontalPose({ ...detection(), keypoints: [{ x: NaN, y: 0 }, { x: 0, y: 0 }, { x: 0, y: 0 }] }, width, height)).toBeNull();
  });

  it('avalia iluminação na região do rosto, sem usar o fundo claro como referência', () => {
    const values = pixels((x, y) => x >= 160 && x < 480 && y >= 48 && y < 432 ? 20 : 180);
    expect(illuminationMessage(values, width, height, face)).toContain('muito escuro');
  });

  it('distingue rosto escuro, superexposição, saturação e baixo contraste', () => {
    expect(illuminationMessage(pixels(() => 20), width, height, face)).toContain('muito escuro');
    expect(illuminationMessage(pixels(() => 240), width, height, face)).toContain('luz excessiva');
    expect(illuminationMessage(pixels((x) => x < 320 ? 0 : 255), width, height, face)).toContain('sombras intensas');
    expect(illuminationMessage(pixels(() => 100), width, height, face)).toContain('pouco contraste');
    expect(illuminationMessage(pixels((x) => x < 320 ? 70 : 170), width, height, face)).toBeNull();
  });

  it('sem rosto detectado, só atribui a falha à exposição quando a imagem inteira é extrema', () => {
    expect(frameExposureMessage(pixels(() => 10))).toContain('muito escura');
    expect(frameExposureMessage(pixels(() => 250))).toContain('luz excessiva');
    expect(frameExposureMessage(pixels(() => 100))).toBeNull();
  });

  it('exige o rosto inteiro dentro do guia', () => {
    expect(faceInsideGuide(face, width, height)).toBe(true);
    expect(faceInsideGuide({ ...face, originX: 600 }, width, height)).toBe(false);
  });
});
