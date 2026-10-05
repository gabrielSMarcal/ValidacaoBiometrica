export interface Frame {
  largura: number;
  altura: number;
  rgb_base64: string;
}

export interface Captura {
  frames: Frame[]; // entre 3 e 5 itens
}
