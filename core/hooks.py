import importlib.util
import logging
import inspect
import os

class HookManager:
    def __init__(self, hook_path=None):
        self.logger = logging.getLogger("HookManager")
        self.module = None
        
        if hook_path:
            if not os.path.exists(hook_path):
                self.logger.warning(f"Hook file not found: {hook_path}")
                return
                
            try:
                # 파일 경로에서 모듈을 동적으로 로드
                spec = importlib.util.spec_from_file_location("custom_hook", hook_path)
                self.module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(self.module)
                self.logger.info(f"Loaded custom hooks from: {hook_path}")
            except Exception as e:
                self.logger.error(f"Failed to load hook: {e}")

    async def run(self, event_name, *args, **kwargs):
        """
        이벤트 이름(예: 'before_request')에 해당하는 함수가 있으면 실행
        """
        if self.module and hasattr(self.module, event_name):
            func = getattr(self.module, event_name)
            try:
                # 비동기 함수면 await, 아니면 그냥 실행
                if inspect.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                return func(*args, **kwargs)
            except Exception as e:
                self.logger.error(f"Error running hook '{event_name}': {e}")
                # 에러 발생 시 원본 데이터를 그대로 반환하여 파이프라인이 끊기지 않게 함
                return args[0] if args else None
        
        # 훅이 없으면 첫 번째 인자를 그대로 통과시킴 (Pass-through)
        return args[0] if args else None