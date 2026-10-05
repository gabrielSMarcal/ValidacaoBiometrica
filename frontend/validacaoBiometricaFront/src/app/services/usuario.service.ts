import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';

// Models
import { Usuario } from '../model/usuario/usuario.model';
import { UsuarioCadastro } from '../model/usuario/usuario-cadastro.model';
import { ValidationError } from '../model/validation-error/validation-error.model';
import { BiometriaRequest } from '../model/biometria/biometria.model';
import { Credenciais } from '../model/autenticacao/autenticacao.model';
import { VerificacaoRequest } from '../model/autenticacao/verificacao.model';

@Injectable({
  providedIn: 'root'
})
export class UsuarioService {
  private apiUrl = 'http://localhost:8000/api';

  constructor(private http: HttpClient) {}

  // 🔹 Cadastrar usuário
  cadastrarUsuario(dados: UsuarioCadastro): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/usuarios`, dados).pipe(
      catchError(err => {
        if (err.status === 422) {
          const erros: ValidationError[] = err.error.detail;
          return throwError(() => erros);
        }
        return throwError(() => err);
      })
    );
  }

  // 🔹 Atualizar usuário
  atualizarUsuario(id: number, dados: any): Observable<Usuario> {
    return this.http.patch<Usuario>(`${this.apiUrl}/usuarios/${id}`, dados).pipe(
      catchError(err => {
        if (err.status === 422) {
          const erros: ValidationError[] = err.error.detail;
          return throwError(() => erros);
        }
        return throwError(() => err);
      })
    );
  }

  // 🔹 Excluir usuário
  excluirUsuario(id: number): Observable<void> {
    return this.http.delete<void>(`${this.apiUrl}/usuarios/${id}`).pipe(
      catchError(err => {
        if (err.status === 422) {
          const erros: ValidationError[] = err.error.detail;
          return throwError(() => erros);
        }
        return throwError(() => err);
      })
    );
  }

  // 🔹 Atualizar biometria
  atualizarBiometria(id: number, dados: BiometriaRequest): Observable<any> {
    return this.http.put<any>(`${this.apiUrl}/usuarios/${id}/biometria`, dados).pipe(
      catchError(err => {
        if (err.status === 422) {
          const erros: ValidationError[] = err.error.detail;
          return throwError(() => erros);
        }
        return throwError(() => err);
      })
    );
  }

  // 🔹 Autenticar usuário (login)
  autenticarUsuario(dados: Credenciais): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/autenticacao/credenciais`, dados).pipe(
      catchError(err => {
        if (err.status === 422) {
          const erros: ValidationError[] = err.error.detail;
          return throwError(() => erros);
        }
        return throwError(() => err);
      })
    );
  }

  verificarBiometria(dados: VerificacaoRequest): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/autenticacao/verificar`, dados).pipe(
        catchError(err => {
        if (err.status === 422) {
            const erros: ValidationError[] = err.error.detail;
            return throwError(() => erros);
        }
        return throwError(() => err);
        })
    );
    }

 obterSessao(): Observable<any> {
    return this.http.get<any>(`${this.apiUrl}/sessao`).pipe(
        catchError(err => {
        return throwError(() => err);
        })
    );
    }
   
 sairSessao(): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/sair`, {}).pipe(
        catchError(err => {
        return throwError(() => err);
        })
    );
    }

}
