export interface Usuario {
  id: number;
  nome: string;
  nivel: number;
}

export interface UsuarioAdministrativo extends Usuario {
  ativo: boolean;
  criado_em: string;
}

export interface UsuarioResponse {
  usuario: Usuario;
}

export interface UsuariosResponse {
  usuarios: UsuarioAdministrativo[];
}

export interface ProcessamentoBiometria {
  [etapa: string]: unknown;
}

export interface UsuarioComProcessamentoResponse extends UsuarioResponse {
  processamento: ProcessamentoBiometria;
}
