import { apiClient } from './api';
import {
  HumanReviewPayload,
  ResearchRequest,
  RevisionResponse,
  WorkflowDetailResponse,
} from '../types';

export const workflowService = {
  async startWorkflow(data: ResearchRequest): Promise<WorkflowDetailResponse> {
    const response = await apiClient.post<WorkflowDetailResponse>('/workflows/start', data);
    return response.data;
  },

  async getWorkflow(workflowId: string): Promise<WorkflowDetailResponse> {
    const response = await apiClient.get<WorkflowDetailResponse>(`/workflows/${workflowId}`);
    return response.data;
  },

  async listWorkflows(statusFilter?: string): Promise<WorkflowDetailResponse[]> {
    const params = statusFilter ? { status: statusFilter } : {};
    const response = await apiClient.get<WorkflowDetailResponse[]>('/workflows', { params });
    return response.data;
  },

  async submitReview(
    workflowId: string,
    payload: HumanReviewPayload
  ): Promise<WorkflowDetailResponse> {
    const response = await apiClient.post<WorkflowDetailResponse>(
      `/workflows/${workflowId}/review`,
      payload
    );
    return response.data;
  },

  async getRevisions(workflowId: string): Promise<RevisionResponse[]> {
    const response = await apiClient.get<RevisionResponse[]>(`/workflows/${workflowId}/revisions`);
    return response.data;
  },

  async deleteWorkflow(workflowId: string): Promise<void> {
    await apiClient.delete(`/workflows/${workflowId}`);
  },
};
