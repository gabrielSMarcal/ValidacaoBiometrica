export interface Frame {
  largura: number;
  altura: number;
  y0_base64: string;
}

export interface UsuarioCadastro {
  frames: Frame[];
  cpf: string;
  nome: string;
  nivel: number;
}
