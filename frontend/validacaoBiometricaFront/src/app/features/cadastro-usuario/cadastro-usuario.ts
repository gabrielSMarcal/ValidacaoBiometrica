import { Component, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiError } from '../../core/models/validation-error/api-error.model';
import { UsuarioService } from '../../core/services/usuario.service';

@Component({
  imports: [ReactiveFormsModule, RouterLink],
  selector: 'app-cadastro-usuario',
  styleUrl: './cadastro-usuario.css',
  templateUrl: './cadastro-usuario.html',
})
export class CadastroUsuario {
  protected readonly form = inject(NonNullableFormBuilder).group({
    nome: ['', [Validators.required, Validators.minLength(2)]],
    cpf: ['', [Validators.required]],
    senha: ['', [Validators.required, Validators.minLength(8)]],
    nivel: [1, [Validators.required, Validators.min(1), Validators.max(3)]],
  });
  protected readonly statusMessage = signal('Preencha os dados para criar o usuário.');
  protected readonly errorMessage = signal('');
  protected readonly submitting = signal(false);

  private readonly usuarioService = inject(UsuarioService);
  private readonly router = inject(Router);

  async cadastrar(): Promise<void> {
    if (this.form.invalid || this.submitting()) {
      this.form.markAllAsTouched();
      return;
    }

    this.submitting.set(true);
    this.errorMessage.set('');
    try {
      const response = await firstValueFrom(this.usuarioService.cadastrarUsuario({
        ...this.form.getRawValue(),
      }));
      if (response.usuario.nivel === 4) {
        await this.router.navigateByUrl('/painel-admin');
      } else {
        await this.router.navigate(['/reconhecimento-facial'], {
          queryParams: { cadastroId: response.usuario.id },
        });
      }
    } catch (error: unknown) {
      this.errorMessage.set(this.getErrorMessage(error));
      this.statusMessage.set('O cadastro não foi concluído.');
    } finally {
      this.submitting.set(false);
    }
  }

  private getErrorMessage(error: unknown): string {
    const apiError = typeof error === 'object' && error !== null
      ? error as Partial<ApiError>
      : {};
    if (apiError.status === 0) {
      return 'Não foi possível conectar ao serviço. Verifique sua conexão e tente novamente.';
    }
    if (typeof apiError.detail === 'string' && apiError.detail.trim()) {
      return apiError.detail;
    }
    if (Array.isArray(apiError.detail)) {
      const mensagens = apiError.detail.map((item) => item?.msg).filter(Boolean).join(' ');
      if (mensagens) {
        return mensagens;
      }
    }
    if (apiError.status === 401) {
      return 'Sua sessão expirou. Entre novamente para cadastrar o usuário.';
    }
    if (apiError.status === 403) {
      return 'O cadastro de usuários exige uma sessão de administrador.';
    }
    if (apiError.status === 409) {
      return 'Já existe um usuário com os dados informados. Confira o CPF.';
    }
    if (apiError.status === 429) {
      return 'Muitas tentativas em pouco tempo. Aguarde antes de tentar novamente.';
    }
    return 'Não foi possível cadastrar o usuário. Revise os dados e tente novamente.';
  }

}
