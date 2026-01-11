"""
Data source configuration service.

Provides table names and data source configuration for queries.
This centralizes FINRA-specific table names, allowing commands
to remain domain-agnostic.

In Intermediate tier, this could be extended to support multiple
data sources or dynamic table resolution.
"""


class DataSourceConfig:
    """
    Configuration for data source tables.

    This service encapsulates domain-specific table names,
    keeping commands free of hardcoded FINRA constants.

    Example:
        config = DataSourceConfig()
        table = config.normalized_data_table
        # "finra_otc_transparency_normalized"
    """

    # FINRA OTC Transparency table names
    NORMALIZED_TABLE = "finra_otc_transparency_normalized"
    RAW_TABLE = "finra_otc_transparency_raw"
    AGGREGATED_TABLE = "finra_otc_transparency_aggregated"

    @property
    def normalized_data_table(self) -> str:
        """Get the normalized data table name."""
        return self.NORMALIZED_TABLE

    @property
    def raw_data_table(self) -> str:
        """Get the raw data table name."""
        return self.RAW_TABLE

    @property
    def aggregated_data_table(self) -> str:
        """Get the aggregated data table name."""
        return self.AGGREGATED_TABLE

    def get_table(self, table_type: str) -> str:
        """
        Get a table name by type.

        Args:
            table_type: One of "normalized", "raw", "aggregated"

        Returns:
            Table name string

        Raises:
            ValueError: If table_type is not recognized
        """
        tables = {
            "normalized": self.NORMALIZED_TABLE,
            "raw": self.RAW_TABLE,
            "aggregated": self.AGGREGATED_TABLE,
        }
        if table_type not in tables:
            valid = ", ".join(tables.keys())
            raise ValueError(f"Unknown table type: '{table_type}'. Valid: {valid}")
        return tables[table_type]
