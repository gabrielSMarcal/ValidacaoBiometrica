import { Component, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiError } from '../../core/models/validation-error/api-error.model';
import { AuthService } from '../../core/services/auth.service';

@Component({
  imports: [ReactiveFormsModule],
  selector: 'app-login-page',
  styleUrl: './login-page.css',
  templateUrl: './login-page.html',
})
export class LoginPage {
  protected readonly errorMessage = signal('');
  protected readonly submitting = signal(false);
  protected readonly form = inject(NonNullableFormBuilder).group({
    cpf: ['', [Validators.required]],
    senha: ['', [Validators.required]],
  });

  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  async onSubmit(): Promise<void> {
    if (this.form.invalid || this.submitting()) {
      this.form.markAllAsTouched();
      return;
    }

    this.submitting.set(true);
    this.errorMessage.set('');

    try {
      const resposta = await firstValueFrom(this.auth.autenticarCredenciais({
        cpf: this.form.controls.cpf.value.trim(),
        senha: this.form.controls.senha.value,
      }));
      await this.router.navigateByUrl(
        this.auth.isAdmin(resposta.usuario) ? '/painel-admin' : '/reconhecimento-facial',
      );
    } catch (error: unknown) {
      this.errorMessage.set(this.describeError(error));
    } finally {
      this.submitting.set(false);
    }
  }

  private describeError(error: unknown): string {
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
      return 'CPF ou senha inválidos. Confira suas credenciais e tente novamente.';
    }
    if (apiError.status === 429) {
      return 'Muitas tentativas em pouco tempo. Aguarde antes de tentar novamente.';
    }
    return 'Não foi possível concluir o acesso. Tente novamente em instantes.';
  }
}
