import { Injectable, signal } from '@angular/core';

import { MockUser } from '../models/autenticacao/mock-user.model';

const MOCK_USERS: readonly MockUser[] = [
  { cpf: '00000000001', senha: 'admin123', nome: 'Administração', nivel: -1 },
  { cpf: '00000000002', senha: 'nivel1abc', nome: 'Usuário de nível 1', nivel: 1 },
  { cpf: '00000000003', senha: 'nivel2abc', nome: 'Usuário de nível 2', nivel: 2 },
  { cpf: '00000000004', senha: 'nivel3abc', nome: 'Usuário de nível 3', nivel: 3 }
];

@Injectable({ providedIn: 'root' })
export class MockAuthService {
  readonly currentUser = signal<MockUser | null>(null);

  autenticar(cpf: string, senha: string): MockUser | null {
    const user = MOCK_USERS.find((candidate) => candidate.cpf === cpf && candidate.senha === senha) ?? null;
    this.currentUser.set(user);
    return user;
  }

  sair(): void {
    this.currentUser.set(null);
  }
}
