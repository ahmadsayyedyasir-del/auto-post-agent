import { apiClient } from './api';
import {
  CredentialDeleteResponse,
  CredentialListResponse,
  CredentialMetadata,
  UpsertCredentialRequest,
} from '../types';

export const credentialService = {
  async upsertCredential(data: UpsertCredentialRequest): Promise<CredentialMetadata> {
    const response = await apiClient.post<CredentialMetadata>('/credentials', data);
    return response.data;
  },

  async listCredentials(): Promise<CredentialListResponse> {
    const response = await apiClient.get<CredentialListResponse>('/credentials');
    return response.data;
  },

  async deleteCredential(
    platform: string,
    credentialKey: string
  ): Promise<CredentialDeleteResponse> {
    const response = await apiClient.delete<CredentialDeleteResponse>(
      `/credentials/${encodeURIComponent(platform)}/${encodeURIComponent(credentialKey)}`
    );
    return response.data;
  },
};
