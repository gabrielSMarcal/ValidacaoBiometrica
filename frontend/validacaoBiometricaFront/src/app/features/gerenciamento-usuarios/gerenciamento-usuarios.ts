import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { UsuarioAtualizacao } from '../../core/models/usuario/usuario-atualizacao.model';
import { UsuarioAdministrativo } from '../../core/models/usuario/usuario.model';
import { UsuarioService } from '../../core/services/usuario.service';

@Component({
  imports: [FormsModule, RouterLink],
  selector: 'app-gerenciamento-usuarios',
  styleUrl: './gerenciamento-usuarios.css',
  templateUrl: './gerenciamento-usuarios.html',
})
export class GerenciamentoUsuarios implements OnInit {
  protected readonly users = signal<UsuarioAdministrativo[]>([]);
  protected readonly loading = signal(true);
  protected readonly errorMessage = signal('');
  protected readonly editingId = signal<number | null>(null);
  protected readonly savingId = signal<number | null>(null);
  protected readonly editing = signal({ nome: '', nivel: 1, senha: '' });

  private readonly usuarioService = inject(UsuarioService);

  ngOnInit(): void {
    void this.loadUsers();
  }

  async toggleActive(user: UsuarioAdministrativo): Promise<void> {
    await this.save(user, { ativo: !user.ativo });
  }

  startEditing(user: UsuarioAdministrativo): void {
    this.editingId.set(user.id);
    this.editing.set({ nome: user.nome, nivel: user.nivel, senha: '' });
  }

  cancelEditing(): void {
    this.editingId.set(null);
  }

  async saveEditing(user: UsuarioAdministrativo): Promise<void> {
    const value = this.editing();
    const changes: UsuarioAtualizacao = { nome: value.nome, nivel: value.nivel };
    if (value.senha) {
      changes.senha = value.senha;
    }
    await this.save(user, changes);
    this.editingId.set(null);
  }

  async remove(user: UsuarioAdministrativo): Promise<void> {
    if (!window.confirm(`Excluir o usuário ${user.nome}?`)) {
      return;
    }
    this.savingId.set(user.id);
    try {
      await firstValueFrom(this.usuarioService.excluirUsuario(user.id));
      this.users.update((users) => users.filter((item) => item.id !== user.id));
    } catch {
      this.errorMessage.set('Não foi possível excluir o usuário.');
    } finally {
      this.savingId.set(null);
    }
  }

  protected updateEditing(field: 'nome' | 'nivel' | 'senha', value: string): void {
    this.editing.update((editing) => ({
      ...editing,
      [field]: field === 'nivel' ? Number(value) : value,
    }));
  }

  private async loadUsers(): Promise<void> {
    try {
      const response = await firstValueFrom(this.usuarioService.listarUsuarios());
      this.users.set(response.usuarios);
    } catch {
      this.errorMessage.set('Não foi possível carregar os usuários.');
    } finally {
      this.loading.set(false);
    }
  }

  private async save(user: UsuarioAdministrativo, changes: UsuarioAtualizacao): Promise<void> {
    this.savingId.set(user.id);
    this.errorMessage.set('');
    try {
      const response = await firstValueFrom(this.usuarioService.atualizarUsuario(user.id, changes));
      this.users.update((users) => users.map((item) =>
        item.id === user.id ? { ...item, ...response.usuario } : item,
      ));
    } catch {
      this.errorMessage.set('Não foi possível atualizar o usuário.');
    } finally {
      this.savingId.set(null);
    }
  }
}
