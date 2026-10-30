import type { Detection } from '@mediapipe/tasks-vision';

export const CAPTURE_POLICY = {
  width: 640,
  height: 480,
  frameCount: 3,
  stableSamples: 3,
  sampleIntervalMs: 200,
  stepTimeoutMs: 15000,
  frontalLimit: 0.12,
  poseLimit: 0.35,
  minimumTurn: 0.075,
} as const;

export const SINGLE_FACE_MESSAGE = 'Deve haver somente uma pessoa na imagem. Afaste as outras pessoas e reinicie a captura.';

export const ENROLLMENT_INSTRUCTIONS = [
  'Etapa 1 de 3: olhe de frente para a câmera e mantenha o rosto dentro do guia.',
  'Etapa 2 de 3: vire levemente o rosto para a sua direita, mantendo os dois olhos visíveis.',
  'Etapa 3 de 3: vire levemente o rosto para a sua esquerda, mantendo os dois olhos visíveis.',
] as const;

export type FaceBox = NonNullable<Detection['boundingBox']>;

export function horizontalPose(detection: Detection, width: number, height: number): number | null {
  // BlazeFace: olhos nos pontos 0/1 e ponta do nariz no ponto 2.
  const keypoints = detection.keypoints.slice(0, 3);
  if (keypoints.length !== 3 || keypoints.some((point) => !Number.isFinite(point.x) || !Number.isFinite(point.y))) {
    return null;
  }
  const eyes = keypoints.slice(0, 2)
    .map((point) => ({ x: point.x * width, y: point.y * height }))
    .sort((left, right) => left.x - right.x);
  const nose = { x: keypoints[2].x * width, y: keypoints[2].y * height };
  const dx = eyes[1].x - eyes[0].x;
  const dy = eyes[1].y - eyes[0].y;
  const squaredDistance = dx * dx + dy * dy;
  if (squaredDistance < 16 * 16) {
    return null;
  }
  return ((nose.x - (eyes[0].x + eyes[1].x) / 2) * dx
    + (nose.y - (eyes[0].y + eyes[1].y) / 2) * dy) / squaredDistance;
}

export function matchesEnrollmentPose(pose: number | null, step: number, frontalPose: number | null): boolean {
  if (pose === null || !Number.isFinite(pose) || Math.abs(pose) > CAPTURE_POLICY.poseLimit) {
    return false;
  }
  if (step === 0) {
    return Math.abs(pose) <= CAPTURE_POLICY.frontalLimit;
  }
  if (frontalPose === null) {
    return false;
  }
  // A prévia é espelhada por CSS; os pixels enviados não são espelhados.
  return step === 1
    ? pose - frontalPose <= -CAPTURE_POLICY.minimumTurn
    : step === 2 && pose - frontalPose >= CAPTURE_POLICY.minimumTurn;
}

export function faceInsideGuide(face: FaceBox, width: number, height: number): boolean {
  const centerX = (face.originX + face.width / 2) / width;
  const centerY = (face.originY + face.height / 2) / height;
  return width > 0 && height > 0
    && face.originX >= 0 && face.originY >= 0
    && face.originX + face.width <= width && face.originY + face.height <= height
    && centerX >= 0.25 && centerX <= 0.75
    && centerY >= 0.1 && centerY <= 0.9
    && face.width / width >= 0.2 && face.width / width <= 0.7
    && face.height / height >= 0.25 && face.height / height <= 0.95;
}

export function frameExposureMessage(pixels: Uint8ClampedArray): string | null {
  let sum = 0;
  let count = 0;
  for (let index = 0; index + 2 < pixels.length; index += 16) {
    sum += pixels[index] * 0.299 + pixels[index + 1] * 0.587 + pixels[index + 2] * 0.114;
    count += 1;
  }
  if (count === 0) {
    return null;
  }
  if (sum / count < 35) {
    return 'A imagem está muito escura para detectar o rosto. Aumente a iluminação à sua frente.';
  }
  return sum / count > 225
    ? 'A imagem está com luz excessiva para detectar o rosto. Reduza a luz direta e os reflexos na câmera.'
    : null;
}

export function illuminationMessage(pixels: Uint8ClampedArray, width: number, height: number, face: FaceBox): string | null {
  const left = Math.max(0, Math.floor(face.originX));
  const top = Math.max(0, Math.floor(face.originY));
  const right = Math.min(width, Math.ceil(face.originX + face.width));
  const bottom = Math.min(height, Math.ceil(face.originY + face.height));
  const centerX = (left + right) / 2;
  const centerY = (top + bottom) / 2;
  const radiusX = (right - left) / 2;
  const radiusY = (bottom - top) / 2;
  let count = 0;
  let sum = 0;
  let squaredSum = 0;
  let saturated = 0;
  for (let y = top; y < bottom; y += 2) {
    for (let x = left; x < right; x += 2) {
      if (radiusX <= 0 || radiusY <= 0
        || ((x - centerX) / radiusX) ** 2 + ((y - centerY) / radiusY) ** 2 > 1) {
        continue;
      }
      const index = (y * width + x) * 4;
      const luminance = pixels[index] * 0.299 + pixels[index + 1] * 0.587 + pixels[index + 2] * 0.114;
      sum += luminance;
      squaredSum += luminance * luminance;
      saturated += luminance <= 8 || luminance >= 247 ? 1 : 0;
      count += 1;
    }
  }
  if (count === 0) {
    return 'Não foi possível avaliar a iluminação. Enquadre o rosto inteiro na câmera.';
  }
  const mean = sum / count;
  if (mean < 35) {
    return 'O rosto está muito escuro. Aumente a iluminação à sua frente e evite luz forte atrás de você.';
  }
  if (mean > 225) {
    return 'Há luz excessiva sobre o rosto. Reduza a luz direta e evite reflexos na câmera.';
  }
  if (saturated / count > 0.55) {
    return 'Há luz direta ou sombras intensas no rosto. Procure uma iluminação uniforme à sua frente.';
  }
  if (Math.sqrt(Math.max(0, squaredSum / count - mean * mean)) < 14) {
    return 'O rosto está com pouco contraste. Ajuste a iluminação à sua frente e permaneça dentro do guia.';
  }
  return null;
}
