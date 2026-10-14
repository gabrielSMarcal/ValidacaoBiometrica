export interface ValidationError {
  loc: (string | number)[]; // localização do erro (campo)
  msg: string;              // mensagem de erro
  type: string;             // tipo de erro
  input?: unknown;          // valor que causou o erro
  ctx?: object;             // contexto adicional
}
