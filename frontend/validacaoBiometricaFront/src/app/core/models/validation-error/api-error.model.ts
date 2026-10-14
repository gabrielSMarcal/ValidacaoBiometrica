import { HTTPValidationError } from './http-validation-error.model';

export interface ApiError {
  status: number;
  detail: HTTPValidationError['detail'] | string;
}
