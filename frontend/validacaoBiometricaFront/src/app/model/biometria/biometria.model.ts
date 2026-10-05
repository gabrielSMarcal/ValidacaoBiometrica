export interface BiometriaFrente {
  largura: number;
  altura: number;
  rgb_base64: string;
}

export interface BiometriaRequest {
  frente: BiometriaFrente[];
}
