import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { Credenciais } from '../models/autenticacao/credenciais.model';
import { VerificacaoRequest } from '../models/autenticacao/verificacao.model';
import { AutenticacaoResponse } from '../models/autenticacao/autenticacao-response.model';
import { BiometriaRequest } from '../models/biometria/biometria.model';
import { UsuarioCadastro } from '../models/usuario/usuario-cadastro.model';
import {
  Usuario,
  UsuarioComProcessamentoResponse,
  UsuarioResponse,
  UsuariosResponse
} from '../models/usuario/usuario.model';
import { UsuarioAtualizacao } from '../models/usuario/usuario-atualizacao.model';
import { ApiError } from '../models/validation-error/api-error.model';
import { SessaoResponse } from '../models/autenticacao/sessao-response.model';

@Injectable({ providedIn: 'root' })
export class UsuarioService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = 'http://localhost:8000/api';
  private readonly withCredentials = { withCredentials: true };

  cadastrarUsuario(dados: UsuarioCadastro): Observable<UsuarioComProcessamentoResponse> {
    return this.request(
      this.http.post<UsuarioComProcessamentoResponse>(`${this.apiUrl}/usuarios`, dados)
    );
  }

  listarUsuarios(): Observable<UsuariosResponse> {
    return this.request(this.http.get<UsuariosResponse>(`${this.apiUrl}/usuarios`));
  }

  atualizarUsuario(id: number, dados: UsuarioAtualizacao): Observable<UsuarioResponse> {
    return this.request(
      this.http.patch<UsuarioResponse>(`${this.apiUrl}/usuarios/${id}`, dados)
    );
  }

  excluirUsuario(id: number): Observable<void> {
    return this.request(this.http.delete<void>(`${this.apiUrl}/usuarios/${id}`));
  }

  atualizarBiometria(
    id: number,
    dados: BiometriaRequest
  ): Observable<UsuarioComProcessamentoResponse> {
    return this.request(
      this.http.put<UsuarioComProcessamentoResponse>(
        `${this.apiUrl}/usuarios/${id}/biometria`,
        dados
      )
    );
  }

  autenticarUsuario(dados: Credenciais): Observable<AutenticacaoResponse> {
    return this.request(
      this.http.post<AutenticacaoResponse>(
        `${this.apiUrl}/autenticacao/credenciais`,
        dados,
        this.withCredentials
      )
    );
  }

  verificarBiometria(dados: VerificacaoRequest): Observable<UsuarioComProcessamentoResponse> {
    return this.request(
      this.http.post<UsuarioComProcessamentoResponse>(
        `${this.apiUrl}/autenticacao/verificar`,
        dados,
        this.withCredentials
      )
    );
  }

  obterSessao(): Observable<SessaoResponse> {
    return this.request(
      this.http.get<SessaoResponse>(`${this.apiUrl}/sessao`, this.withCredentials)
    );
  }

  sairSessao(): Observable<{ mensagem: string }> {
    return this.request(
      this.http.post<{ mensagem: string }>(`${this.apiUrl}/sair`, {}, this.withCredentials)
    );
  }

  private request<T>(request: Observable<T>): Observable<T> {
    return request.pipe(catchError((error: HttpErrorResponse) => {
      const apiError: ApiError = {
        status: error.status,
        detail: error.error?.detail ?? error.message
      };
      return throwError(() => apiError);
    }));
  }
}
