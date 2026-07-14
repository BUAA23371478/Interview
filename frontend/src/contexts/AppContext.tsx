import React, { createContext, useContext, useReducer, useCallback, type ReactNode } from 'react';
import type { User } from '@/types/common';

interface AppState {
  user: User | null;
  isRegistered: boolean;
}

type AppAction =
  | { type: 'SET_USER'; payload: User }
  | { type: 'CLEAR_USER' };

const initialState: AppState = {
  user: null,
  isRegistered: !!localStorage.getItem('userId'),
};

function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case 'SET_USER':
      return {
        ...state,
        user: action.payload,
        isRegistered: true,
      };
    case 'CLEAR_USER':
      return {
        ...state,
        user: null,
        isRegistered: false,
      };
    default:
      return state;
  }
}

interface AppContextType {
  state: AppState;
  setUser: (user: User) => void;
  clearUser: () => void;
  getUserId: () => string | null;
  getUsername: () => string;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export const AppProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [state, dispatch] = useReducer(appReducer, initialState);

  const setUser = useCallback((user: User) => {
    localStorage.setItem('userId', user.userId);
    localStorage.setItem('username', user.username);
    dispatch({ type: 'SET_USER', payload: user });
  }, []);

  const clearUser = useCallback(() => {
    localStorage.removeItem('userId');
    localStorage.removeItem('username');
    dispatch({ type: 'CLEAR_USER' });
  }, []);

  const getUserId = useCallback(() => {
    return localStorage.getItem('userId');
  }, []);

  const getUsername = useCallback(() => {
    return localStorage.getItem('username') || '用户';
  }, []);

  return (
    <AppContext.Provider value={{ state, setUser, clearUser, getUserId, getUsername }}>
      {children}
    </AppContext.Provider>
  );
};

export function useAppContext(): AppContextType {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error('useAppContext must be used within an AppProvider');
  }
  return context;
}

export default AppContext;
