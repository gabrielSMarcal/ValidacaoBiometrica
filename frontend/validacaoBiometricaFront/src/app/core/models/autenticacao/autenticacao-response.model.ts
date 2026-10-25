import { Usuario } from '../usuario/usuario.model';

export interface AutenticacaoResponse {
  mensagem: string;
  expira_em_segundos: number;
  usuario: Pick<Usuario, 'id' | 'nome' | 'nivel'>;
}
