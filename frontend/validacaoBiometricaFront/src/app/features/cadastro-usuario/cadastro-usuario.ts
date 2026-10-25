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
    nivel: [1, [Validators.required, Validators.min(1), Validators.max(4)]],
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
    const apiError = error as Partial<ApiError>;
    return typeof apiError.detail === 'string'
      ? apiError.detail
      : 'Não foi possível cadastrar o usuário.';
  }

}
