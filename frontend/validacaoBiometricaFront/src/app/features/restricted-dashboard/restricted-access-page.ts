import { Component, OnInit, computed, inject } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { EMPTY, catchError } from 'rxjs';

import { AuthService } from '../../core/services/auth.service';

interface RestrictedAccess {
  title: string;
  level: number;
  description: string;
  guidance: string;
}

const ACCESS_BY_PATH: Record<string, RestrictedAccess> = {
  'alertas-ambientais-gerais': {
    title: 'Alertas ambientais gerais',
    level: 1,
    description: 'Acompanhe alertas ambientais gerais e ocorrências fictícias em observação.',
    guidance: 'Consulte os comunicados oficiais antes de compartilhar qualquer informação.',
  },
  'classificacao-publica-de-risco': {
    title: 'Classificação pública de risco das toxinas',
    level: 1,
    description: 'Consulte classificações públicas e não operacionais relacionadas aos riscos.',
    guidance: 'Os dados desta área são demonstrativos e não substituem orientações das autoridades.',
  },
  'comunicados-e-orientacoes': {
    title: 'Comunicados e orientações gerais',
    level: 1,
    description: 'Leia comunicados oficiais e orientações gerais de segurança institucional.',
    guidance: 'Em caso de emergência, siga os canais oficiais de atendimento.',
  },
  'registros-administrativos-de-incidentes': {
    title: 'Registros administrativos de incidentes da toxina',
    level: 2,
    description: 'Acompanhe registros administrativos fictícios, responsáveis e prazos de revisão.',
    guidance: 'Registre atualizações somente pelos fluxos institucionais autorizados.',
  },
  'status-de-conformidade': {
    title: 'Status de conformidade das toxinas',
    level: 2,
    description: 'Monitore pendências, revisões e o status de conformidade dos processos.',
    guidance: 'Os indicadores exibidos são demonstrativos e devem ser validados pela área responsável.',
  },
  'coordenacao-de-equipes-autorizadas': {
    title: 'Coordenação de equipes autorizadas',
    level: 2,
    description: 'Consulte equipes autorizadas, atribuições e o andamento das coordenações.',
    guidance: 'Compartilhe informações de equipe apenas nos canais institucionais.',
  },
  'briefing-estrategico': {
    title: 'Briefing estratégico para decisões ministeriais',
    level: 3,
    description: 'Consulte um resumo estratégico fictício para apoiar decisões ministeriais.',
    guidance: 'Este briefing é demonstrativo e não contém dados operacionais reais.',
  },
  'impactos-em-saude-publica-e-ecossistemas': {
    title: 'Impactos em saúde pública e ecossistemas',
    level: 3,
    description: 'Avalie impactos consolidados e fictícios em saúde pública e ecossistemas.',
    guidance: 'Use os dados como referência institucional e preserve as informações restritas.',
  },
  'orcamento-transparencia-e-comunicacao-de-crise': {
    title: 'Orçamento, transparência e comunicação de crise',
    level: 3,
    description: 'Acompanhe informações demonstrativas de orçamento, transparência e crise.',
    guidance: 'Toda comunicação externa deve seguir a aprovação institucional correspondente.',
  },
};

@Component({
  imports: [RouterLink],
  selector: 'app-restricted-access-page',
  styleUrl: './restricted-access-page.css',
  templateUrl: './restricted-access-page.html',
})
export class RestrictedAccessPage implements OnInit {
  private readonly route = inject(ActivatedRoute);
  protected readonly auth = inject(AuthService);
  protected readonly access = computed(() => {
    const path = this.route.snapshot.paramMap.get('access') ?? '';
    return ACCESS_BY_PATH[path] ?? null;
  });
  protected readonly hasAccess = computed(() => {
    const access = this.access();
    return access !== null && this.auth.currentUser()?.nivel === access.level;
  });

  ngOnInit(): void {
    if (!this.auth.currentUser()) {
      this.auth.carregarSessao().pipe(
        catchError(() => EMPTY),
      ).subscribe();
    }
  }
}
