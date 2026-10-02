import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { Navbar } from './features/navbar/navbar';
import { LoginPage } from './features/login-page/login-page';

@Component({
  selector: 'app-root',
  imports: [Navbar, RouterOutlet, LoginPage],
  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class App { }
