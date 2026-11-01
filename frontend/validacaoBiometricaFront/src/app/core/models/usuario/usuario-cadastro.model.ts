import { Frame } from '../biometria/biometria.model';

export interface UsuarioCadastro {
  frames: Frame[];
  cpf: string;
  senha: string;
  nome: string;
  nivel: number;
}

export type UsuarioCadastroDados = Omit<UsuarioCadastro, 'frames'>;
