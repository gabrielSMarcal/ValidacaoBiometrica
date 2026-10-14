import { Component, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  imports: [RouterLink],
  selector: 'app-navbar',
  styleUrl: './navbar.css',
  templateUrl: './navbar.html',
})
export class Navbar {
  readonly menuOpen = signal(false);

  protected readonly links = [
    { label: 'Sobre', href: '#sobre' },
    { label: 'Prioridades', href: '#prioridades' },
    { label: 'Serviços', href: '#servicos' },
    { label: 'Participação', href: '#participacao' }
  ];

  protected toggleMenu(): void {
    this.menuOpen.update((isOpen) => !isOpen);
  }

  protected closeMenu(): void {
    this.menuOpen.set(false);
  }
}
