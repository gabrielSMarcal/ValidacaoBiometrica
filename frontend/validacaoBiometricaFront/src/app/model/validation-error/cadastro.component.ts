import { Component } from '@angular/core';
import { UsuarioService } from '../services/usuario.service';
import { ValidationError } from '../validation-error/validation-error.model';

@Component({
  selector: 'app-cadastro',
  templateUrl: './cadastro.component.html'
})
export class CadastroComponent {
  errosValidacao: ValidationError[] = [];

  constructor(private usuarioService: UsuarioService) {}

  salvar(dados: any) {
    this.usuarioService.cadastrarUsuario(dados).subscribe({
      next: () => {
        console.log('Cadastro realizado com sucesso');
        this.errosValidacao = [];
      },
      error: (err) => {
        if (Array.isArray(err)) {
          this.errosValidacao = err;
        }
      }
    });
  }
}
