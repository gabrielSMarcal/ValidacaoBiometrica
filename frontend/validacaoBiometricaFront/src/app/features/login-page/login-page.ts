import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { MockAuthService } from '../../core/services/mock-auth.service';

@Component({
  imports: [FormsModule],
  selector: 'app-login-page',
  styleUrl: './login-page.css',
  templateUrl: './login-page.html',
})
export class LoginPage {
  cpf = '';
  password = '';
  errorMessage = '';

  private readonly auth = inject(MockAuthService);
  private readonly router = inject(Router);

  onSubmit(): void {
    const user = this.auth.autenticar(this.cpf.trim(), this.password);

    if (!user) {
      this.errorMessage = 'CPF ou senha inválidos. Use uma das contas de demonstração.';
      return;
    }

    this.errorMessage = '';
    void this.router.navigateByUrl(user.nivel === -1 ? '/painel-admin' : '/reconhecimento-facial');
  }
}
