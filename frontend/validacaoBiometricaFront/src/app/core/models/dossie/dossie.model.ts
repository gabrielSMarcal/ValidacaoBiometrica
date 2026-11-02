export interface DossieDados {
  codigo: string;
  titulo: string;
  situacao: string;
  divisao: string;
  atualizado_em: string;
}

export interface DossieResumo extends DossieDados {
  resumo: string;
  pendencias_abertas: number;
  decisoes_pendentes: number;
}

export interface DossiesResponse {
  nivel: number;
  dossies: DossieResumo[];
}

export interface DossieCampo {
  rotulo: string;
  valor: string;
}

export interface DossieItem {
  titulo: string;
  descricao: string | null;
  prazo: string | null;
  situacao: string | null;
}

export interface DossieEvento {
  data: string | null;
  descricao: string;
}

export interface DossieRecorte {
  nivel: number;
  resumo: string;
  orientacao: string;
  campos: DossieCampo[];
  pendencias: DossieItem[];
  decisoes: DossieItem[];
  historico: DossieEvento[];
}

export interface DossieDetalheResponse {
  nivel: number;
  dossie: DossieDados;
  recorte: DossieRecorte;
}
