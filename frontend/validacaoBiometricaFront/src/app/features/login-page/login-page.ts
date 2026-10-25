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
    const apiError = error as Partial<ApiError>;
    if (apiError.status === 401) {
      return 'CPF ou senha inválidos.';
    }
    if (typeof apiError.detail === 'string') {
      return apiError.detail;
    }
    return 'Não foi possível acessar o sistema. Tente novamente.';
  }
}
