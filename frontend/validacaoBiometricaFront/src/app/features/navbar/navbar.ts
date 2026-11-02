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
    { label: 'Sobre', fragment: 'sobre' },
    { label: 'Prioridades', fragment: 'prioridades' },
    { label: 'Serviços', fragment: 'servicos' },
    { label: 'Participação', fragment: 'participacao' }
  ];

  protected toggleMenu(): void {
    this.menuOpen.update((isOpen) => !isOpen);
  }

  protected closeMenu(): void {
    this.menuOpen.set(false);
  }
}
