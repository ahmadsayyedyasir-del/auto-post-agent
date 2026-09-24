import { apiClient } from './api';
import {
  PublicationListResponse,
  PublicationResponse,
  PublishWorkflowRequest,
} from '../types';

export const publicationService = {
  async publishWorkflow(
    workflowId: string,
    payload?: PublishWorkflowRequest
  ): Promise<PublicationResponse> {
    const response = await apiClient.post<PublicationResponse>(
      `/workflows/${workflowId}/publish`,
      payload || {}
    );
    return response.data;
  },

  async getWorkflowPublications(workflowId: string): Promise<PublicationListResponse> {
    const response = await apiClient.get<PublicationListResponse>(
      `/workflows/${workflowId}/publication`
    );
    return response.data;
  },

  async getPublication(publicationId: string): Promise<PublicationResponse> {
    const response = await apiClient.get<PublicationResponse>(
      `/publications/${publicationId}`
    );
    return response.data;
  },

  async retryPublication(publicationId: string): Promise<PublicationResponse> {
    const response = await apiClient.post<PublicationResponse>(
      `/publications/${publicationId}/retry`
    );
    return response.data;
  },
};
