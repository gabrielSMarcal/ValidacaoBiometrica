export interface Frame {
  largura: number;
  altura: number;
  rgb_base64: string;
}

export interface BiometriaRequest {
  frames: Frame[];
}
