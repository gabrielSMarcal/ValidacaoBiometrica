import { Component } from '@angular/core';
import { FormBuilder, Validators, FormArray } from '@angular/forms';

@Component({
  selector: 'app-cadastro',
  templateUrl: './cadastro.component.html'
})
export class CadastroComponent {
  cadastroForm = this.fb.group({
    frames: this.fb.array([], [Validators.minLength(3), Validators.maxLength(5)]),
    cpf: ['', [Validators.required, Validators.minLength(11), Validators.maxLength(18)]],
    senha: ['', [Validators.required, Validators.minLength(8), Validators.maxLength(128)]],
    nome: ['', [Validators.required, Validators.minLength(2), Validators.maxLength(120)]],
    nivel: [1, [Validators.required, Validators.min(1), Validators.max(3)]]
  });

  constructor(private fb: FormBuilder) {}

  get frames(): FormArray {
    return this.cadastroForm.get('frames') as FormArray;
  }

  addFrame() {
    this.frames.push(this.fb.group({
      largura: [160, [Validators.min(160), Validators.max(640)]],
      altura: [120, [Validators.min(120), Validators.max(480)]],
      rgb_base64: ['', [Validators.required]]
    }));
  }

  salvar() {
    if (this.cadastroForm.valid) {
      console.log(this.cadastroForm.value);
      // aqui você envia para o backend
    }
  }
}
