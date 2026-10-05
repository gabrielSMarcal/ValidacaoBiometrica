import { Component } from '@angular/core';
import { FormBuilder, Validators, FormArray } from '@angular/forms';

@Component({
  selector: 'app-captura',
  templateUrl: './captura.component.html'
})
export class CapturaComponent {
  capturaForm = this.fb.group({
    frames: this.fb.array([], [Validators.minLength(3), Validators.maxLength(5)])
  });

  constructor(private fb: FormBuilder) {}

  get frames(): FormArray {
    return this.capturaForm.get('frames') as FormArray;
  }

  addFrame() {
    this.frames.push(this.fb.group({
      largura: [160, [Validators.min(160), Validators.max(640)]],
      altura: [120, [Validators.min(120), Validators.max(480)]],
      rgb_base64: ['', [Validators.required]]
    }));
  }

  salvar() {
    if (this.capturaForm.valid) {
      console.log(this.capturaForm.value);
      // aqui você envia para o backend
    }
  }
}
