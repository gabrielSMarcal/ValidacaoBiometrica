import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Navbar } from './navbar';

describe('Navbar', () => {
  let component: Navbar;
  let fixture: ComponentFixture<Navbar>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Navbar],
    }).compileComponents();

    fixture = TestBed.createComponent(Navbar);
    component = fixture.componentInstance;
    fixture.detectChanges();
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should toggle the mobile menu', async () => {
    const button = fixture.nativeElement.querySelector('button') as HTMLButtonElement;
    expect(component.menuOpen()).toBe(false);

    button.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(component.menuOpen()).toBe(true);
  });
});
