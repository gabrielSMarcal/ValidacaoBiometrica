import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { DossieDetalheResponse, DossiesResponse } from '../models/dossie/dossie.model';
import { ApiError } from '../models/validation-error/api-error.model';

/** Consulta os dossiês; o servidor decide qual recorte cada nível recebe. */
@Injectable({ providedIn: 'root' })
export class DossieService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = 'http://localhost:8000/api';
  private readonly withCredentials = { withCredentials: true };

  listarDossies(): Observable<DossiesResponse> {
    return this.request(
      this.http.get<DossiesResponse>(`${this.apiUrl}/dossies`, this.withCredentials)
    );
  }

  consultarDossie(codigo: string): Observable<DossieDetalheResponse> {
    return this.request(
      this.http.get<DossieDetalheResponse>(
        `${this.apiUrl}/dossies/${encodeURIComponent(codigo)}`, this.withCredentials
      )
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

/** Converte AAAA-MM-DD em DD/MM/AAAA sem depender do fuso horário. */
export function formatarData(iso: string | null): string {
  if (!iso) {
    return '';
  }
  const [ano, mes, dia] = iso.slice(0, 10).split('-');
  return `${dia}/${mes}/${ano}`;
}

export function rotuloNivel(nivel: number): string {
  switch (nivel) {
    case 1:
      return 'Permissão geral';
    case 2:
      return 'Diretor de divisão';
    case 3:
      return 'Ministro do Meio Ambiente';
    default:
      return 'Acesso não identificado';
  }
}

/** Tom visual da etiqueta de situação: informação, alerta, concluído ou reservado. */
export function tomSituacao(situacao: string | null): string {
  switch (situacao) {
    case 'Concluída':
    case 'Registrada':
      return 'concluido';
    case 'Aberta':
    case 'Pendente':
    case 'Pendências em aberto':
    case 'Aguardando decisão':
      return 'alerta';
    case 'Reservado ao ministro':
      return 'reservado';
    default:
      return 'info';
  }
}

export function plural(quantidade: number, singular: string, pluralizado: string): string {
  return `${quantidade} ${quantidade === 1 ? singular : pluralizado}`;
}
