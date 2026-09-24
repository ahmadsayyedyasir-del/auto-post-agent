import { apiClient } from './api';
import {
  CreateScheduleRequest,
  ScheduleListResponse,
  ScheduleResponse,
  UpdateScheduleRequest,
} from '../types';

export const scheduleService = {
  async createSchedule(data: CreateScheduleRequest): Promise<ScheduleResponse> {
    const response = await apiClient.post<ScheduleResponse>('/schedules', data);
    return response.data;
  },

  async listSchedules(params?: {
    workflow_id?: string;
    status?: string;
    platform?: string;
  }): Promise<ScheduleListResponse> {
    const response = await apiClient.get<ScheduleListResponse>('/schedules', { params });
    return response.data;
  },

  async getSchedule(scheduleId: string): Promise<ScheduleResponse> {
    const response = await apiClient.get<ScheduleResponse>(`/schedules/${scheduleId}`);
    return response.data;
  },

  async updateSchedule(
    scheduleId: string,
    data: UpdateScheduleRequest
  ): Promise<ScheduleResponse> {
    const response = await apiClient.patch<ScheduleResponse>(
      `/schedules/${scheduleId}`,
      data
    );
    return response.data;
  },

  async cancelSchedule(scheduleId: string): Promise<ScheduleResponse> {
    const response = await apiClient.delete<ScheduleResponse>(`/schedules/${scheduleId}`);
    return response.data;
  },

  async runScheduleNow(scheduleId: string): Promise<ScheduleResponse> {
    const response = await apiClient.post<ScheduleResponse>(`/schedules/${scheduleId}/run`);
    return response.data;
  },
};
