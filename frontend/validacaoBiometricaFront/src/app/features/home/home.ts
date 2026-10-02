import { Component } from '@angular/core';

@Component({
  selector: 'app-home',
  templateUrl: './home.html',
  styleUrl: './home.css'
})
export class HomeComponent {
  protected readonly priorities = [
    {
      eyebrow: 'Proteção territorial',
      title: 'Combate ao desmatamento, à grilagem e às queimadas',
      description:
        'Ações integradas de monitoramento, fiscalização e prevenção para proteger biomas, povos e comunidades tradicionais.'
    },
    {
      eyebrow: 'Clima e adaptação',
      title: 'Resiliência para cidades, campo e infraestrutura',
      description:
        'Instrumentos de adaptação climática para apoiar gestores públicos, setores produtivos e populações vulneráveis.'
    },
    {
      eyebrow: 'Economia verde',
      title: 'Transição ecológica com emprego e inovação',
      description:
        'Políticas que valorizam energia limpa, bioeconomia, restauração e cadeias produtivas de baixo carbono.'
    }
  ];

  protected readonly services = [
    {
      title: 'Licenciamento e autorizações',
      description: 'Orientações e consultas para processos ambientais com mais transparência e previsibilidade.'
    },
    {
      title: 'Dados e monitoramento',
      description: 'Acesso a indicadores, mapas e painéis para acompanhar desmatamento, fogo e qualidade ambiental.'
    },
    {
      title: 'Participação social',
      description: 'Canais para conselhos, consultas públicas e escuta da sociedade na formulação de políticas.'
    }
  ];

  protected readonly commitments = [
    'Zerar o desmatamento ilegal até 2030.',
    'Ampliar a restauração de áreas degradadas.',
    'Fortalecer a governança climática em todos os níveis.',
    'Promover justiça socioambiental e inclusão.'
  ];
}
