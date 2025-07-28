import os
from dotenv import load_dotenv
import logging
import json
from pydantic_settings import BaseSettings
from typing import Optional, Dict
from pydantic import field_validator, ConfigDict, ConfigDict

load_dotenv()

class Settings(BaseSettings):
    """应用程序设置类，使用Pydantic进行类型验证和环境变量管理"""

    # --- 从 .env 文件读取的必需配置 ---
    BINANCE_API_KEY: str = ""  # 添加默认值以便测试
    BINANCE_API_SECRET: str = ""  # 添加默认值以便测试

    # --- 策略核心配置 (从 .env 读取) ---
    SYMBOLS: str = "BNB/USDT"  # 从 .env 读取交易对列表字符串

    # 按交易对设置的初始参数 (JSON格式)
    INITIAL_PARAMS_JSON: Dict[str, Dict[str, float]] = {}

    INITIAL_GRID: float = 2.0  # 全局默认网格大小
    MIN_TRADE_AMOUNT: float = 20.0

    # --- 初始状态设置 (从 .env 读取) ---
    INITIAL_PRINCIPAL: float = 0.0

    # --- 可选配置 (从 .env 读取) ---
    PUSHPLUS_TOKEN: Optional[str] = None
    NOTIFICATION_PLATFORM: Optional[str] = None
    TELEGRAM_TOKEN: Optional[str] = None
    TELEGRAM_CHANNEL_ID: Optional[str] = None

    # 理财功能开关
    ENABLE_SAVINGS_FUNCTION: bool = True

    WEB_USER: Optional[str] = None
    WEB_PASSWORD: Optional[str] = None
    HTTP_PROXY: Optional[str] = None

    # --- 理财精度配置 (从JSON字符串解析) ---
    SAVINGS_PRECISIONS: Dict[str, int] = {'USDT': 2, 'BNB': 6, 'DEFAULT': 8}

    # --- 新增：从 .env 读取的高级策略配置 ---
    GRID_PARAMS_JSON: Dict = {}
    GRID_CONTINUOUS_PARAMS_JSON: Dict = {}
    DYNAMIC_INTERVAL_PARAMS_JSON: Dict = {}
    ENABLE_VOLUME_WEIGHTING: bool = True

    @field_validator('INITIAL_PARAMS_JSON', mode='before')
    @classmethod
    def parse_initial_params(cls, value):
        """解析按交易对设置的初始参数JSON字符串"""
        if isinstance(value, str) and value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                raise ValueError("INITIAL_PARAMS_JSON 格式无效，必须是合法的JSON字符串。")
        return value if value else {}  # 如果为空，返回空字典

    @field_validator('GRID_PARAMS_JSON', 'GRID_CONTINUOUS_PARAMS_JSON', 'DYNAMIC_INTERVAL_PARAMS_JSON', mode='before')
    @classmethod
    def parse_strategy_params_json(cls, value):
        """通用验证器，用于将策略相关的JSON字符串解析为字典"""
        if isinstance(value, str) and value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                raise ValueError(f"策略参数格式无效，必须是合法的JSON字符串。收到的值: {value}")
        return value if value else {}

    @field_validator('SAVINGS_PRECISIONS', mode='before')
    @classmethod
    def parse_savings_precisions(cls, value):
        """自定义验证器，用于将JSON字符串解析为字典"""
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                raise ValueError("SAVINGS_PRECISIONS 格式无效，必须是合法的JSON字符串。")
        return value

    # --- 固定配置 (不常修改，保留在代码中) ---
    MIN_POSITION_PERCENT: float = 0.05
    MAX_POSITION_PERCENT: float = 0.15
    MAX_POSITION_RATIO: float = 0.9
    MIN_POSITION_RATIO: float = 0.1
    COOLDOWN: int = 60
    SAFETY_MARGIN: float = 0.95
    AUTO_ADJUST_BASE_PRICE: bool = False
    PUSHPLUS_TIMEOUT: int = 5
    LOG_LEVEL: int = logging.INFO
    DEBUG_MODE: bool = False
    API_TIMEOUT: int = 10000
    RECV_WINDOW: int = 5000
    RISK_CHECK_INTERVAL: int = 300
    MAX_RETRIES: int = 5
    RISK_FACTOR: float = 0.1
    VOLATILITY_WINDOW: int = 52  # 52日窗口
    VOLATILITY_EWMA_LAMBDA: float = 0.94  # EWMA衰减因子 (RiskMetrics标准)
    VOLATILITY_HYBRID_WEIGHT: float = 0.7  # EWMA权重，传统波动率权重为0.3
    POSITION_SCALE_FACTOR: float = 0.2

    # 常量化魔术数字
    SPOT_FUNDS_TARGET_RATIO: float = 0.16
    MIN_BNB_TRANSFER: float = 0.01

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding='utf-8',
        case_sensitive=True,
        extra='ignore'  # 忽略额外的字段
    )

# 创建全局设置实例
settings = Settings()

# 提供一个解析后的列表，方便使用
SYMBOLS_LIST = [s.strip() for s in settings.SYMBOLS.split(',') if s.strip()]

# 保留必要的向后兼容性常量，但建议逐步迁移到 settings.XXX 的形式
FLIP_THRESHOLD = lambda grid_size: (grid_size / 5) / 100  # 网格大小的1/5的1%

class TradingConfig:
    """
    交易配置类，现在只包含从settings派生或转换而来的复杂策略参数。
    简单的配置项直接从全局的 settings 对象获取。

    这个类的职责：
    1. 将JSON格式的策略参数转换为Python字典
    2. 为复杂的策略参数提供默认值
    3. 进行配置验证
    """

    RISK_PARAMS = {
        'position_limit': settings.MAX_POSITION_RATIO
    }

    # 将硬编码的字典替换为从 settings 中获取，如果为空则使用默认值
    GRID_PARAMS = settings.GRID_PARAMS_JSON if settings.GRID_PARAMS_JSON else {
        'initial': settings.INITIAL_GRID,
        'min': 1.0,  # 网格大小的绝对最小值
        'max': 4.0,  # 网格大小的绝对最大值
        'volatility_threshold': {
            'ranges': [
                # --- 更直接、更敏感的波动率-网格映射关系 ---
                {'range': [0, 0.10], 'grid': 1.0},      # 波动率 0% 到 10% (不含)，网格 1.0%
                {'range': [0.10, 0.20], 'grid': 2.0},   # 波动率 10% 到 20% (不含)，网格 2.0%
                {'range': [0.20, 0.30], 'grid': 3.0},   # 波动率 20% 到 30% (不含)，网格 3.0%
                {'range': [0.30, 0.40], 'grid': 4.0},   # 波动率 30% 到 40% (不含)，网格 4.0%
                {'range': [0.40, 999], 'grid': 4.0}     # 波动率 40% 及以上，统一使用最大网格 4.0%
            ]
        }
    }

    # 连续网格调整参数
    GRID_CONTINUOUS_PARAMS = settings.GRID_CONTINUOUS_PARAMS_JSON if settings.GRID_CONTINUOUS_PARAMS_JSON else {
        'base_grid': 2.5,          # 波动率处于中心点时，我们期望的基础网格大小 (例如 2.5%)
        'center_volatility': 0.25, # 我们定义的市场"正常"波动率水平 (例如 0.25 或 25%)
        'sensitivity_k': 10.0      # 灵敏度系数k。k越大，网格对波动率变化的反应越剧烈。
                                   # k=10.0 意味着波动率每变化1%(0.01)，网格大小变化 0.1% (10.0 * 0.01)
    }

    # 成交量加权波动率计算开关
    ENABLE_VOLUME_WEIGHTING = settings.ENABLE_VOLUME_WEIGHTING

    # 动态时间间隔参数
    DYNAMIC_INTERVAL_PARAMS = settings.DYNAMIC_INTERVAL_PARAMS_JSON if settings.DYNAMIC_INTERVAL_PARAMS_JSON else {
        # 定义波动率区间与对应调整间隔（小时）的映射关系
        'volatility_to_interval_hours': [
            # 格式: {'range': [最低波动率(含), 最高波动率(不含)], 'interval_hours': 对应的小时间隔}
            # --- 与新的网格映射保持一致的时间间隔 ---
            {'range': [0, 0.10], 'interval_hours': 1.0},      # 波动率 < 10%，每 1 小时检查一次
            {'range': [0.10, 0.20], 'interval_hours': 0.5},   # 波动率 10-20%，每 30 分钟检查一次
            {'range': [0.20, 0.30], 'interval_hours': 0.25},  # 波动率 20-30%，每 15 分钟检查一次
            {'range': [0.30, 999], 'interval_hours': 0.125},  # 波动率 > 30%，每 7.5 分钟检查一次
        ],
        # 定义一个默认间隔，以防波动率计算失败或未匹配到任何区间
        'default_interval_hours': 1.0
    }

    # 保留的策略相关基础值
    BASE_AMOUNT = 50.0  # 基础交易金额（可调整）

    def __init__(self):
        # 添加配置验证
        if settings.MIN_POSITION_RATIO >= settings.MAX_POSITION_RATIO:
            raise ValueError("底仓比例不能大于或等于最大仓位比例")

        if self.GRID_PARAMS['min'] > self.GRID_PARAMS['max']:
            raise ValueError("网格最小值不能大于最大值")

        # API密钥验证已由Pydantic在settings实例化时自动完成

        # 验证数值范围
        if settings.INITIAL_PRINCIPAL < 0:
            raise ValueError("INITIAL_PRINCIPAL不能为负数")

        # INITIAL_BASE_PRICE已移除，现在使用INITIAL_PARAMS_JSON中的交易对特定配置
        
    # Removed unused update methods (update_risk_params, update_grid_params, 
    # update_symbol, update_initial_base_price, update_risk_check_interval, 
    # update_max_retries, update_risk_factor, update_base_amount, 
    # update_min_trade_amount, update_max_position_ratio, 
    # update_min_position_ratio, update_all)

    # Removed unused validate_config method
# End of class definition 
