export interface Frame {
  largura: number;
  altura: number;
  rgb_base64: string;
}

export interface Cadastro {
  frames: Frame[];
  cpf: string;
  senha: string;
  nome: string;
  nivel: number;
}
