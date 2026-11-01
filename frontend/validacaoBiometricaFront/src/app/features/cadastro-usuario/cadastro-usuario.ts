import { Component, inject, signal } from '@angular/core';
import { AbstractControl, NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { CadastroPendenteService } from '../../core/services/cadastro-pendente.service';

function validarCpf(control: AbstractControl): { cpf: true } | null {
  const value = String(control.value ?? '');
  const cpf = value.replace(/[.\- ]/g, '');
  if (!/^[0-9.\- ]{11,18}$/.test(value) || !/^\d{11}$/.test(cpf) || /^(\d)\1{10}$/.test(cpf)) {
    return { cpf: true };
  }
  for (const tamanho of [9, 10]) {
    let soma = 0;
    for (let i = 0; i < tamanho; i += 1) {
      soma += Number(cpf[i]) * (tamanho + 1 - i);
    }
    if ((soma * 10 % 11) % 10 !== Number(cpf[tamanho])) {
      return { cpf: true };
    }
  }
  return null;
}

@Component({
  imports: [ReactiveFormsModule, RouterLink],
  selector: 'app-cadastro-usuario',
  styleUrl: './cadastro-usuario.css',
  templateUrl: './cadastro-usuario.html',
})
export class CadastroUsuario {
  protected readonly form = inject(NonNullableFormBuilder).group({
    nome: ['', [Validators.required, Validators.pattern(/\S(?:.*\S)/), Validators.maxLength(120)]],
    cpf: ['', [Validators.required, validarCpf]],
    senha: ['', [Validators.required, Validators.minLength(8), Validators.maxLength(128)]],
    nivel: [1, [Validators.required, Validators.min(1), Validators.max(3)]],
  });
  protected readonly statusMessage = signal('O usuário será cadastrado somente após concluir a captura facial.');
  protected readonly errorMessage = signal('');
  protected readonly submitting = signal(false);

  private readonly cadastroPendente = inject(CadastroPendenteService);
  private readonly router = inject(Router);

  async cadastrar(): Promise<void> {
    if (this.form.invalid || this.submitting()) {
      this.form.markAllAsTouched();
      this.errorMessage.set('Informe nome, CPF válido, senha de 8 a 128 caracteres e nível de acesso.');
      return;
    }

    this.submitting.set(true);
    this.errorMessage.set('');
    try {
      this.cadastroPendente.iniciar(this.form.getRawValue());
      const navigated = await this.router.navigate(['/reconhecimento-facial'], {
        queryParams: { cadastro: 'novo' },
      });
      if (!navigated) {
        throw new Error('Não foi possível abrir a captura facial. Tente continuar novamente.');
      }
    } catch (error: unknown) {
      this.cadastroPendente.limpar();
      this.errorMessage.set(error instanceof Error ? error.message : 'Não foi possível abrir a captura facial. Tente novamente.');
      this.statusMessage.set('O cadastro não foi concluído.');
    } finally {
      this.submitting.set(false);
    }
  }

}
