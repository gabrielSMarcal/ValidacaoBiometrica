import { Component } from '@angular/core';
import { FormsModule } from '@angular/forms';

@Component({
  imports: [FormsModule],
  selector: 'app-login-page',
  styleUrl: './login-page.css',
  templateUrl: './login-page.html',
})
export class LoginPage {
  cpf: string = '';
  password: string = '';

  onSubmit() {
    console.log('cpf: ', this.cpf, 'pw: ', this.password)
  }
}
