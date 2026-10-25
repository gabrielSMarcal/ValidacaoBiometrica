import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { RestrictedDashboard } from './restricted-dashboard';

describe('RestrictedDashboard', () => {
  let component: RestrictedDashboard;
  let fixture: ComponentFixture<RestrictedDashboard>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [RestrictedDashboard],
      providers: [provideHttpClient(), provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(RestrictedDashboard);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
