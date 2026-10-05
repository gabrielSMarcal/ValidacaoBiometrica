import { Component } from '@angular/core';
import { FormBuilder, Validators } from '@angular/forms';

@Component({
  selector: 'app-frame',
  templateUrl: './frame.component.html'
})
export class FrameComponent {
  frameForm = this.fb.group({
    largura: [160, [Validators.required, Validators.min(160), Validators.max(640)]],
    altura: [120, [Validators.required, Validators.min(120), Validators.max(480)]],
    rgb_base64: ['', [Validators.required, Validators.minLength(1), Validators.maxLength(1228800)]]
  });

  constructor(private fb: FormBuilder) {}

  salvar() {
    if (this.frameForm.valid) {
      console.log(this.frameForm.value);
      // aqui você envia para o backend
    }
  }
}
