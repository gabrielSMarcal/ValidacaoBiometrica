export interface FrameVerificacao {
  largura: number;
  altura: number;
  rgb_base64: string;
}

export interface VerificacaoRequest {
  frames: FrameVerificacao[];
}
