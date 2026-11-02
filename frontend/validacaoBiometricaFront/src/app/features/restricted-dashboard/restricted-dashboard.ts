import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { EMPTY, catchError } from 'rxjs';

import { DossieResumo } from '../../core/models/dossie/dossie.model';
import { ApiError } from '../../core/models/validation-error/api-error.model';
import { AuthService } from '../../core/services/auth.service';
import {
  DossieService,
  formatarData,
  plural,
  rotuloNivel,
  tomSituacao,
} from '../../core/services/dossie.service';

type EstadoPainel = 'carregando' | 'pronto' | 'sessao' | 'administrador' | 'erro';

interface Indicador {
  rotulo: string;
  valor: string;
  detalhe: string;
}

@Component({
  imports: [RouterLink],
  selector: 'app-restricted-dashboard',
  styleUrl: './restricted-dashboard.css',
  templateUrl: './restricted-dashboard.html',
})
export class RestrictedDashboard implements OnInit {
  protected readonly auth = inject(AuthService);
  private readonly dossieService = inject(DossieService);

  protected readonly estado = signal<EstadoPainel>('carregando');
  protected readonly dossies = signal<DossieResumo[]>([]);
  protected readonly mensagemErro = signal('');
  private readonly nivelServidor = signal(0);

  protected readonly level = computed(() => this.auth.currentUser()?.nivel ?? this.nivelServidor());
  protected readonly accessLabel = computed(() => rotuloNivel(this.level()));
  protected readonly mostrarCabecalho = computed(() =>
    this.level() >= 1 && this.level() <= 3 && this.estado() !== 'sessao' && this.estado() !== 'administrador');
  protected readonly indicadores = computed<Indicador[]>(() => {
    const dossies = this.dossies();
    const ultima = dossies.map((dossie) => dossie.atualizado_em).sort().at(-1) ?? null;
    const lista: Indicador[] = [{
      rotulo: 'Dossiês autorizados',
      valor: String(dossies.length),
      detalhe: 'Liberados pelo servidor para o seu nível',
    }];

    if (this.level() === 2) {
      lista.push({
        rotulo: 'Pendências abertas',
        valor: String(dossies.reduce((total, dossie) => total + dossie.pendencias_abertas, 0)),
        detalhe: 'Aguardando ação das divisões',
      });
    }
    if (this.level() === 3) {
      lista.push({
        rotulo: 'Decisões pendentes',
        valor: String(dossies.reduce((total, dossie) => total + dossie.decisoes_pendentes, 0)),
        detalhe: 'Aguardando deliberação do ministro',
      });
    }
    lista.push({
      rotulo: 'Última atualização',
      valor: ultima ? formatarData(ultima) : '—',
      detalhe: 'Registro mais recente entre os dossiês',
    });
    return lista;
  });

  protected readonly formatarData = formatarData;
  protected readonly plural = plural;
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
    this.dossieService.listarDossies().subscribe({
      next: (resposta) => {
        this.nivelServidor.set(resposta.nivel);
        this.dossies.set(resposta.dossies);
        this.estado.set('pronto');
      },
      error: (erro: ApiError) => this.tratarErro(erro),
    });
  }

  protected rotaDossie(codigo: string): string[] {
    return ['/restricted-dashboard', codigo.toLowerCase()];
  }

  private tratarErro(erro: ApiError): void {
    if (erro.status === 401) {
      this.estado.set('sessao');
      return;
    }
    if (erro.status === 403) {
      this.estado.set('administrador');
      return;
    }
    this.mensagemErro.set(erro.status === 0
      ? 'Não foi possível conectar à API. Confira se o backend está em execução.'
      : typeof erro.detail === 'string' ? erro.detail : 'Não foi possível carregar os dossiês.');
    this.estado.set('erro');
  }
}
