import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { EMPTY, catchError } from 'rxjs';

import { DossieDetalheResponse, DossieItem } from '../../core/models/dossie/dossie.model';
import { ApiError } from '../../core/models/validation-error/api-error.model';
import { AuthService } from '../../core/services/auth.service';
import {
  DossieService,
  formatarData,
  rotuloNivel,
  tomSituacao,
} from '../../core/services/dossie.service';

type EstadoDossie = 'carregando' | 'pronto' | 'negado' | 'sessao' | 'administrador' | 'erro';

const TITULO_RESUMO: Record<number, string> = {
  1: 'Resumo autorizado',
  2: 'Situação administrativa',
  3: 'Síntese estratégica',
};

@Component({
  imports: [RouterLink],
  selector: 'app-restricted-access-page',
  styleUrl: './restricted-access-page.css',
  templateUrl: './restricted-access-page.html',
})
export class RestrictedAccessPage implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly auth = inject(AuthService);
  private readonly dossieService = inject(DossieService);

  protected readonly codigo = (this.route.snapshot.paramMap.get('access') ?? '').toUpperCase();
  protected readonly estado = signal<EstadoDossie>('carregando');
  protected readonly detalhe = signal<DossieDetalheResponse | null>(null);
  protected readonly mensagemErro = signal('');

  protected readonly nivel = computed(() => this.detalhe()?.recorte.nivel ?? this.auth.currentUser()?.nivel ?? 0);
  protected readonly tituloResumo = computed(() => TITULO_RESUMO[this.nivel()] ?? 'Resumo autorizado');

  protected readonly formatarData = formatarData;
  protected readonly rotuloNivel = rotuloNivel;
  protected readonly tomSituacao = tomSituacao;

  ngOnInit(): void {
    if (!this.auth.currentUser()) {
      this.auth.carregarSessao().pipe(
        catchError(() => EMPTY),
      ).subscribe();
    }
    this.carregar();
  }

  protected carregar(): void {
    this.estado.set('carregando');
    this.dossieService.consultarDossie(this.codigo).subscribe({
      next: (resposta) => {
        this.detalhe.set(resposta);
        this.estado.set('pronto');
      },
      error: (erro: ApiError) => this.tratarErro(erro),
    });
  }

  protected concluido(item: DossieItem): boolean {
    return tomSituacao(item.situacao) === 'concluido';
  }

  private tratarErro(erro: ApiError): void {
    const estados: Record<number, EstadoDossie> = { 401: 'sessao', 403: 'administrador', 404: 'negado' };
    if (estados[erro.status]) {
      this.estado.set(estados[erro.status]);
      return;
    }
    this.mensagemErro.set(erro.status === 0
      ? 'Não foi possível conectar à API. Confira se o backend está em execução.'
      : typeof erro.detail === 'string' ? erro.detail : 'Não foi possível carregar o dossiê.');
    this.estado.set('erro');
  }
}
