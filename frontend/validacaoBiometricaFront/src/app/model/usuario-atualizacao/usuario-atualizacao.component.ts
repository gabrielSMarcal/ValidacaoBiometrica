import { Component } from '@angular/core';
import { FormBuilder } from '@angular/forms';

@Component({
  selector: 'app-usuario-atualizacao',
  templateUrl: './usuario-atualizacao.component.html'
})
export class UsuarioAtualizacaoComponent {
  usuarioForm = this.fb.group({
    nome: [null],
    nivel: [null],
    ativo: [null],
    senha: [null]
  });

  constructor(private fb: FormBuilder) {}

  atualizar() {
    const dados: UsuarioAtualizacao = this.usuarioForm.value;
    console.log(dados);
  }
}
