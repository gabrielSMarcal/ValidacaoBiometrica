import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    loadComponent: () => import('./features/home/home').then((m) => m.HomeComponent)
  },
  {
    path: 'login',
    loadComponent: () => import('./features/login-page/login-page').then((m) => m.LoginPage)
  },
  {
    path: '**',
    redirectTo: ''
  }
];
