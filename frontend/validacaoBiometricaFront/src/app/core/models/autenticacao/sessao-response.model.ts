import { Usuario } from '../usuario/usuario.model';

export interface SessaoResponse {
  usuario: Pick<Usuario, 'id' | 'nome' | 'nivel'>;
  mensagem: string;
}
