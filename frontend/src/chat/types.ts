export type ChatRole = 'user' | 'assistant';

export type ChatMessage = {
  id: string | number;
  role: ChatRole;
  content: string;
};
