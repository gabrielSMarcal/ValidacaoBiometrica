import { Component, OnInit, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { EMPTY, catchError } from 'rxjs';

import { AuthService } from '../../core/services/auth.service';

interface DashboardAccess {
  title: string;
  description: string;
  path: string;
}

@Component({
  imports: [RouterLink],
  selector: 'app-restricted-dashboard',
  styleUrl: './restricted-dashboard.css',
  templateUrl: './restricted-dashboard.html',
})
export class RestrictedDashboard implements OnInit {
  protected readonly auth = inject(AuthService);
  protected readonly level = computed(() => this.auth.currentUser()?.nivel ?? 0);
  protected readonly dashboardAccess = computed<DashboardAccess[]>(() => {
    const accessesByLevel: Record<number, DashboardAccess[]> = {
      1: [
        {
          title: 'Alertas ambientais gerais',
          description: 'Consulte alertas e ocorrências ambientais em acompanhamento.',
          path: 'alertas-ambientais-gerais',
        },
        {
          title: 'Classificação pública de risco das toxinas',
          description: 'Veja classificações públicas e não operacionais de risco.',
          path: 'classificacao-publica-de-risco',
        },
        {
          title: 'Comunicados e orientações gerais',
          description: 'Acesse comunicados oficiais e orientações para a população.',
          path: 'comunicados-e-orientacoes',
        },
      ],
      2: [
        {
          title: 'Registros administrativos de incidentes da toxina',
          description: 'Acompanhe registros, responsáveis e prazos administrativos.',
          path: 'registros-administrativos-de-incidentes',
        },
        {
          title: 'Status de conformidade das toxinas',
          description: 'Monitore pendências, revisões e indicadores de conformidade.',
          path: 'status-de-conformidade',
        },
        {
          title: 'Coordenação de equipes autorizadas',
          description: 'Coordene equipes autorizadas e acompanhe suas atribuições.',
          path: 'coordenacao-de-equipes-autorizadas',
        },
      ],
      3: [
        {
          title: 'Briefing estratégico para decisões ministeriais',
          description: 'Consulte informações estratégicas para decisões ministeriais.',
          path: 'briefing-estrategico',
        },
        {
          title: 'Impactos em saúde pública e ecossistemas',
          description: 'Avalie impactos consolidados em saúde pública e ecossistemas.',
          path: 'impactos-em-saude-publica-e-ecossistemas',
        },
        {
          title: 'Orçamento, transparência e comunicação de crise',
          description: 'Acompanhe orçamento, transparência e comunicação institucional.',
          path: 'orcamento-transparencia-e-comunicacao-de-crise',
        },
      ],
    };

    return accessesByLevel[this.level()] ?? [];
  });
  protected readonly accessLabel = computed(() => {
    switch (this.level()) {
      case 1:
        return 'Acesso geral';
      case 2:
        return 'Diretoria de divisão';
      case 3:
        return 'Gabinete ministerial';
      default:
        return 'Acesso não identificado';
    }
  });

  ngOnInit(): void {
    if (!this.auth.currentUser()) {
      this.auth.carregarSessao().pipe(
        catchError(() => EMPTY),
      ).subscribe();
    }
  }
}
