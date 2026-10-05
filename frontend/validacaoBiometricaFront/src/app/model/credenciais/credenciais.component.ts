import { Component } from '@angular/core';
import { FormBuilder, Validators } from '@angular/forms';

@Component({
  selector: 'app-credenciais',
  templateUrl: './credenciais.component.html'
})
export class CredenciaisComponent {
  credenciaisForm = this.fb.group({
    cpf: ['', [Validators.required, Validators.minLength(11), Validators.maxLength(18)]],
    senha: ['', [Validators.required, Validators.minLength(8), Validators.maxLength(128)]]
  });

  constructor(private fb: FormBuilder) {}

  login() {
    if (this.credenciaisForm.valid) {
      console.log(this.credenciaisForm.value);
      // aqui você envia para o backend (ex.: POST /api/login)
    }
  }
}
