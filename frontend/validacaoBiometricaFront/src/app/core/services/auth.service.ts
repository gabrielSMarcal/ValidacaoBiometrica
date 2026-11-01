import { Injectable, inject, signal } from '@angular/core';
import { Observable, finalize, tap } from 'rxjs';

import { Credenciais } from '../models/autenticacao/credenciais.model';
import { SessaoResponse } from '../models/autenticacao/sessao-response.model';
import { AutenticacaoResponse } from '../models/autenticacao/autenticacao-response.model';
import { UsuarioComProcessamentoResponse } from '../models/usuario/usuario.model';
import { UsuarioService } from './usuario.service';

@Injectable({ providedIn: 'root' })
export class AuthService {
  readonly currentUser = signal<SessaoResponse['usuario'] | null>(null);
  readonly pendingUser = signal<AutenticacaoResponse['usuario'] | null>(null);
  readonly authenticating = signal(false);
  private readonly usuarioService = inject(UsuarioService);

  autenticarCredenciais(dados: Credenciais): Observable<AutenticacaoResponse> {
    this.authenticating.set(true);
    this.currentUser.set(null);
    this.pendingUser.set(null);
    return this.usuarioService.autenticarUsuario(dados).pipe(
      tap((resposta) => {
        if (this.isAdmin(resposta.usuario)) {
          this.currentUser.set(resposta.usuario);
        } else {
          this.pendingUser.set(resposta.usuario);
        }
      }),
      finalize(() => this.authenticating.set(false)),
    );
  }

  isAdmin(usuario: AutenticacaoResponse['usuario'] | null): boolean {
    return usuario?.nivel === 4;
  }

  concluirAutenticacao(resposta: UsuarioComProcessamentoResponse): void {
    this.currentUser.set(resposta.usuario);
    this.pendingUser.set(null);
    this.authenticating.set(false);
  }

  carregarSessao(): Observable<SessaoResponse> {
    return this.usuarioService.obterSessao().pipe(
      tap((sessao) => this.currentUser.set(sessao.usuario)),
    );
  }

  sair(): Observable<{ mensagem: string }> {
    return this.usuarioService.sairSessao().pipe(
      tap(() => {
        this.currentUser.set(null);
        this.pendingUser.set(null);
      }),
    );
  }
}
