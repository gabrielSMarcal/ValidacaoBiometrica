import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { PainelAdmin } from './painel-admin';

describe('PainelAdmin', () => {
  let component: PainelAdmin;
  let fixture: ComponentFixture<PainelAdmin>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PainelAdmin],
      providers: [provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(PainelAdmin);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
