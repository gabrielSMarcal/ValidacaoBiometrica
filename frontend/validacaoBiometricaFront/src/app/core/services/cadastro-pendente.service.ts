import { Injectable, signal } from '@angular/core';

import { UsuarioCadastroDados } from '../models/usuario/usuario-cadastro.model';

@Injectable({ providedIn: 'root' })
export class CadastroPendenteService {
  private readonly rascunho = signal<UsuarioCadastroDados | null>(null);
  readonly dados = this.rascunho.asReadonly();

  iniciar(dados: UsuarioCadastroDados): void {
    // Os dados ficam somente em memória até a conclusão da captura facial.
    this.rascunho.set({ ...dados, nome: dados.nome.trim().replace(/\s+/g, ' ') });
  }

  limpar(): void {
    this.rascunho.set(null);
  }
}
